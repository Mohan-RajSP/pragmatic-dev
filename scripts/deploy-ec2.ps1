<#
.SYNOPSIS
  Redeploy the backend/worker on the EC2 host after pushing new images to ECR.

.DESCRIPTION
  Option A (EC2 + docker-compose) redeploy. Runs entirely over SSM Session
  Manager (no SSH). On the instance it:
    1. Re-authenticates Docker to ECR (instance profile creds).
    2. `docker compose pull` (fetch the new :latest images).
    3. `docker compose up -d` (recreate changed containers).
    4. Prunes old images.
  Then, unless -SkipVerify, curls https://api.pragmatic-dev.in/health from here.

  Pairs with scripts/deploy-backend.ps1 (which builds + pushes the images).
  Typical flow:  .\scripts\deploy-backend.ps1 ;  .\scripts\deploy-ec2.ps1

.PARAMETER InstanceId
  Target EC2 instance. Defaults to the pragmatic-dev host.

.PARAMETER Region
  AWS region. Defaults to ap-south-1.

.PARAMETER SkipVerify
  Don't run the post-deploy HTTPS health check.

.EXAMPLE
  .\scripts\deploy-ec2.ps1
  .\scripts\deploy-ec2.ps1 -SkipVerify
#>
[CmdletBinding()]
param(
  [string]$InstanceId = "i-0e2c5e7f1b3bc0fd2",
  [string]$Region     = "ap-south-1",
  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$Account = "498341975274"
$Registry = "$Account.dkr.ecr.$Region.amazonaws.com"
$AppDir = "/opt/pragmatic-dev"

function Write-Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }

# Remote script: re-auth to ECR, pull, up -d, prune. Single-quoted here-string so
# nothing is expanded locally; $Registry etc. are interpolated below via -f.
$remote = @'
set -e
cd {0}
aws ecr get-login-password --region {1} | docker login --username AWS --password-stdin {2}
export ECR_REGISTRY={2}
docker compose -f docker-compose.ec2.yml pull
docker compose -f docker-compose.ec2.yml up -d
docker image prune -f
echo "---- compose ps ----"
docker compose -f docker-compose.ec2.yml ps
'@ -f $AppDir, $Region, $Registry

# SSM send-command wants the commands as a JSON array; write to a temp param file.
$paramFile = Join-Path ([System.IO.Path]::GetTempPath()) ("ssm-redeploy-" + [Guid]::NewGuid().ToString("N") + ".json")
@{ commands = @($remote) } | ConvertTo-Json -Depth 4 | Set-Content $paramFile -Encoding ascii

Write-Step "Dispatching redeploy to $InstanceId via SSM"
$cid = (aws ssm send-command --instance-ids $InstanceId --document-name "AWS-RunShellScript" `
    --comment "pragmatic-dev EC2 redeploy" --parameters "file://$paramFile" `
    --region $Region --query "Command.CommandId" --output text)
Remove-Item -Force $paramFile -ErrorAction SilentlyContinue
if (-not $cid) { throw "Failed to dispatch SSM command." }
Write-Host "  command id: $cid" -ForegroundColor DarkGray

Write-Step "Waiting for completion"
do {
  Start-Sleep -Seconds 5
  $status = (aws ssm get-command-invocation --command-id $cid --instance-id $InstanceId --region $Region --query "Status" --output text 2>$null)
  Write-Host "  status: $status" -ForegroundColor DarkGray
} while ($status -in @("Pending", "InProgress", "Delayed", ""))

$out = (aws ssm get-command-invocation --command-id $cid --instance-id $InstanceId --region $Region --query "StandardOutputContent" --output text)
$err = (aws ssm get-command-invocation --command-id $cid --instance-id $InstanceId --region $Region --query "StandardErrorContent" --output text)
Write-Host "`n--- remote stdout ---" -ForegroundColor DarkGray
Write-Host $out
if ($err) { Write-Host "--- remote stderr ---" -ForegroundColor Yellow; Write-Host $err }

if ($status -ne "Success") { throw "Redeploy command status: $status" }
Write-Host "`nRedeploy complete." -ForegroundColor Green

if (-not $SkipVerify) {
  Write-Step "Verifying https://api.pragmatic-dev.in/health"
  $code = (curl.exe -s -o NUL -w "%{http_code}" https://api.pragmatic-dev.in/health)
  if ($code -eq "200") { Write-Host "  health = 200 OK" -ForegroundColor Green }
  else { Write-Host "  health = $code (check the stack)" -ForegroundColor Red }
}

