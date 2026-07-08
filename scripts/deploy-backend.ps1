<#
.SYNOPSIS
  Build the backend + worker images and push them to Amazon ECR.

.DESCRIPTION
  Phase 7a of the AWS runbook: container registry + images. Idempotent.

  Steps:
    1. Ensures the ECR repositories exist (creates them if missing).
    2. Logs Docker in to the ECR registry.
    3. Builds the backend and worker images from their Dockerfiles.
    4. Tags each image with both the given -Tag and `latest`, then pushes.

  Later phases (secrets, ElastiCache, VPC/SGs, ECS services, ALB, DNS) are NOT
  handled here -- this only gets the images into ECR.

.PARAMETER Tag
  Image tag to push (in addition to `latest`). Defaults to a UTC timestamp so
  every run is uniquely addressable by an ECS task definition.

.PARAMETER Region
  AWS region for ECR. Defaults to the CLI's configured region (ap-south-1).

.PARAMETER Components
  Which images to build/push. Defaults to both. e.g. -Components backend

.PARAMETER SkipPush
  Build (and create repos) but do not docker push -- useful for a local test build.

.EXAMPLE
  .\scripts\deploy-backend.ps1                       # build + push both, timestamp tag
  .\scripts\deploy-backend.ps1 -Tag v1              # build + push both as :v1 and :latest
  .\scripts\deploy-backend.ps1 -Components worker   # only the worker image
  .\scripts\deploy-backend.ps1 -SkipPush            # local build only (no push)

.NOTES
  Requires Docker to be available on PATH (Docker Desktop WSL2 integration, or run
  this from a shell where `docker` resolves). The backend and worker share the same
  repo layout: images build from ./backend and ./worker respectively.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $false)]
  [string]$Tag = ((Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")),

  [Parameter(Mandatory = $false)]
  [string]$Region,

  [Parameter(Mandatory = $false)]
  [ValidateSet("backend", "worker")]
  [string[]]$Components = @("backend", "worker"),

  [switch]$SkipPush
)

# NOTE: Use 'Continue' (not 'Stop'). Native CLIs (aws, docker) write normal
# progress/notices to stderr; under 'Stop' in Windows PowerShell 5.1 that stderr
# is promoted to a terminating NativeCommandError, which would abort the script
# mid-build. Real failures are still caught via explicit $LASTEXITCODE checks +
# throw after each native call below.
$ErrorActionPreference = "Continue"

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

# --- Preflight -------------------------------------------------------------
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker not found on PATH. Start Docker (Desktop WSL2 integration) or run from a shell where 'docker' resolves."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker daemon not reachable. Is Docker running?" }

if (-not $Region) { $Region = (aws configure get region) }
if (-not $Region) { throw "No AWS region set. Pass -Region or run 'aws configure'." }

$Account = (aws sts get-caller-identity --query Account --output text)
if ($LASTEXITCODE -ne 0 -or -not $Account) { throw "Unable to resolve AWS account (aws sts get-caller-identity failed)." }
$Registry = "$Account.dkr.ecr.$Region.amazonaws.com"

# Resolve repo paths relative to this script so it works from any CWD.
$RepoRoot = Split-Path -Parent $PSScriptRoot

# component -> (ecr repo name, build context dir)
$Map = @{
  backend = @{ Repo = "pragmatic-dev/backend"; Context = (Join-Path $RepoRoot "backend") }
  worker  = @{ Repo = "pragmatic-dev/worker";  Context = (Join-Path $RepoRoot "worker") }
}

Write-Host ("`nRegistry: {0} | Region: {1} | Tag: {2} | Components: {3} | SkipPush: {4}" -f `
    $Registry, $Region, $Tag, ($Components -join ","), [bool]$SkipPush) -ForegroundColor DarkGray

# 1. Ensure ECR repositories exist -----------------------------------------
foreach ($c in $Components) {
  $repo = $Map[$c].Repo
  Write-Step "Ensuring ECR repo: $repo"
  aws ecr describe-repositories --repository-names $repo --region $Region *> $null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "  creating $repo ..." -ForegroundColor Yellow
    aws ecr create-repository `
      --repository-name $repo `
      --image-scanning-configuration scanOnPush=true `
      --image-tag-mutability MUTABLE `
      --region $Region | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create ECR repo $repo" }
  }
  else {
    Write-Host "  exists." -ForegroundColor DarkGray
  }
}

# 2. Docker login to ECR ----------------------------------------------------
# NOTE: We deliberately AVOID `docker login`. On this machine ~/.docker/config.json
# has "credsStore": "desktop", so `docker login` shells out to
# docker-credential-desktop.exe, which BLOCKS forever in a non-interactive shell
# (observed: aws-getpw DONE / docker-images DONE / docker-login HUNG >40s).
# Instead we inject the ECR token directly into an isolated DOCKER_CONFIG that has
# NO credsStore/credHelpers, then point every later docker call at it via the
# DOCKER_CONFIG env var. This fully sidesteps the credential helper.
if (-not $SkipPush) {
  Write-Step "Authenticating to $Registry (helper-free auth injection)"

  $pw = (aws ecr get-login-password --region $Region)
  if ($LASTEXITCODE -ne 0 -or -not $pw) { throw "aws ecr get-login-password failed" }

  $auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("AWS:$pw"))

  $DockerCfgDir = Join-Path ([System.IO.Path]::GetTempPath()) ("ecrcfg-" + [Guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $DockerCfgDir | Out-Null
  $cfgJson = @{ auths = @{ $Registry = @{ auth = $auth } } } | ConvertTo-Json -Depth 5 -Compress
  Set-Content -Path (Join-Path $DockerCfgDir "config.json") -Value $cfgJson -Encoding ascii

  # Redirect ALL subsequent docker calls (build/push) at this helper-free config.
  $env:DOCKER_CONFIG = $DockerCfgDir
  Write-Host "  auth injected -> DOCKER_CONFIG=$DockerCfgDir" -ForegroundColor DarkGray
}

# 3 + 4. Build, tag, push ---------------------------------------------------
foreach ($c in $Components) {
  $repo = $Map[$c].Repo
  $context = $Map[$c].Context
  if (-not (Test-Path (Join-Path $context "Dockerfile"))) { throw "Dockerfile not found in $context" }

  $imageTagged = "${Registry}/${repo}:${Tag}"
  $imageLatest = "${Registry}/${repo}:latest"

  Write-Step "Building $c -> $imageTagged"
  docker build -t $imageTagged -t $imageLatest $context
  if ($LASTEXITCODE -ne 0) { throw "docker build failed for $c" }

  if (-not $SkipPush) {
    Write-Step "Pushing $c"
    docker push $imageTagged
    if ($LASTEXITCODE -ne 0) { throw "docker push failed for ${imageTagged}" }
    docker push $imageLatest
    if ($LASTEXITCODE -ne 0) { throw "docker push failed for ${imageLatest}" }
  }
}

Write-Host "`nDone. Images available in ECR:" -ForegroundColor Green
foreach ($c in $Components) {
  Write-Host ("  {0}/{1}:{2}  (+ :latest)" -f $Registry, $Map[$c].Repo, $Tag) -ForegroundColor Green
}
if ($SkipPush) { Write-Host "(built locally only; -SkipPush set, nothing pushed)" -ForegroundColor Yellow }

# Cleanup: remove the isolated DOCKER_CONFIG (holds a short-lived ECR token).
if ($DockerCfgDir -and (Test-Path $DockerCfgDir)) {
  Remove-Item -Recurse -Force $DockerCfgDir -ErrorAction SilentlyContinue
  Remove-Item Env:\DOCKER_CONFIG -ErrorAction SilentlyContinue
}

