<#
.SYNOPSIS
  Build all three frontend apps (production) and deploy them to S3 + CloudFront.

.DESCRIPTION
  One-command build -> sync -> invalidate cycle for the Pragmatic-dev frontend.

  Steps:
    1. Runs `npm run build` for tipsapp, queryapp, and baseapp (production mode).
    2. Syncs each dist/ to the S3 bucket (excludes source maps).
       - JS bundles/assets get Cache-Control: public,max-age=<BundleMaxAge> (default 1 day).
       - index.html is uploaded with `no-cache` so the entry point is always fresh.
    3. Invalidates CloudFront `/*` so the edge serves the new bundles immediately
       (skipped only if -DistributionId is set to "").

.PARAMETER Bucket
  Target S3 bucket name (no s3:// prefix). Defaults to the prod origin bucket.

.PARAMETER DistributionId
  CloudFront distribution id to invalidate. Defaults to the prod distribution.
  Pass "" to skip invalidation.

.PARAMETER BundleMaxAge
  Cache-Control max-age (seconds) for JS bundles/assets. Default 0 => `no-cache`,
  so the browser always revalidates with the CDN before reusing a bundle (demo-safe:
  every browser sees changes at once, since our bundle filenames are fixed/not hashed).
  Pass a positive value (e.g. 86400) to allow browsers to cache bundles for that long.

.PARAMETER SkipBuild
  Skip the npm builds and deploy whatever is already in each dist/ folder.

.PARAMETER DryRun
  Preview only: S3 steps use --dryrun and the invalidation is printed, not created.

.EXAMPLE
  .\scripts\deploy-frontend.ps1                     # build + deploy (bundles no-cache)
  .\scripts\deploy-frontend.ps1 -DryRun             # preview
  .\scripts\deploy-frontend.ps1 -BundleMaxAge 86400 # let browsers cache bundles 1 day
  .\scripts\deploy-frontend.ps1 -SkipBuild          # redeploy existing dist/

.NOTES
  Our MFE bundles have FIXED filenames (pragmatic-dev-*.js) because the SystemJS
  import-map references those exact URLs -- they are NOT content-hashed. CloudFront
  invalidation clears the EDGE cache (CloudFront re-reads the current S3 object) but
  does NOT clear END-USER BROWSER caches. Hence bundles default to `no-cache` so the
  browser always revalidates with the CDN, and we invalidate /* on every deploy so the
  edge is always fresh -- together every user picks up new bundles immediately.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $false)]
  [string]$Bucket = "pragmatic-dev-frontend-498341975274-ap-south-1-an",

  [Parameter(Mandatory = $false)]
  [string]$DistributionId = "E1OHD40X5ASPPS",

  [Parameter(Mandatory = $false)]
  [int]$BundleMaxAge = 0,

  [switch]$SkipBuild,

  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Resolve repo paths relative to this script so it works from any CWD.
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $RepoRoot "frontend"
$Apps = @("tipsapp", "queryapp", "baseapp")
$S3 = "s3://$Bucket"

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

# 1. Build ------------------------------------------------------------------
if (-not $SkipBuild) {
  foreach ($app in $Apps) {
    Write-Step "Building $app"
    Push-Location (Join-Path $Frontend $app)
    try {
      npm run build
      if ($LASTEXITCODE -ne 0) { throw "Build failed for $app" }
    }
    finally { Pop-Location }
  }
}
else {
  Write-Step "Skipping build (-SkipBuild)"
}

# 2. Sync -------------------------------------------------------------------
# Two MFEs first, shell last. Bundles keep FIXED names, so we rely on the
# per-deploy CloudFront /* invalidation (below) to roll the edge cache, plus
# `no-cache` on bundles so browsers always revalidate. We do NOT use --delete: all
# three apps share one bucket, so a per-app --delete would wipe the other apps' files.
if ($BundleMaxAge -le 0) { $BundleCache = "no-cache" } else { $BundleCache = "public,max-age=$BundleMaxAge" }
$DryRunFlag = if ($DryRun) { "--dryrun" } else { $null }

Write-Host ("`nBundle Cache-Control: {0} | index.html: no-cache | DryRun: {1}" -f $BundleCache, [bool]$DryRun) -ForegroundColor DarkGray

foreach ($app in $Apps) {
  Write-Step "Syncing $app -> $S3"
  $dist = Join-Path $Frontend "$app\dist"
  if (-not (Test-Path $dist)) { throw "dist/ not found for $app at $dist. Run without -SkipBuild first." }
  $syncArgs = @("s3", "sync", $dist, $S3, "--exclude", "*.map", "--exclude", "index.html", "--cache-control", $BundleCache)
  if ($DryRunFlag) { $syncArgs += $DryRunFlag }
  aws @syncArgs
  if ($LASTEXITCODE -ne 0) { throw "s3 sync failed for $app" }
}

# 2b. GUARANTEE bundle Cache-Control ---------------------------------------
# `aws s3 sync` compares only size/mtime, so when a bundle's CONTENT is
# unchanged it is SKIPPED and any metadata-only change (like a new
# Cache-Control) is NOT applied. Force it with an in-place recursive copy
# (--metadata-directive REPLACE rewrites metadata on every .js object).
# Scoped to *.js so we don't reset Content-Type on other asset types.
Write-Step "Enforcing Cache-Control ($BundleCache) on *.js bundles"
$metaArgs = @("s3", "cp", "$S3/", "$S3/", "--recursive", "--exclude", "*", "--include", "*.js",
  "--metadata-directive", "REPLACE", "--cache-control", $BundleCache,
  "--content-type", "application/javascript")
if ($DryRunFlag) { $metaArgs += $DryRunFlag }
aws @metaArgs
if ($LASTEXITCODE -ne 0) { throw "Failed to enforce Cache-Control on bundles" }

# 3. index.html must never be cached (points at the current bundle names).
Write-Step "Uploading index.html -> no-cache"
$IndexHtml = Join-Path $Frontend "baseapp\dist\index.html"
if (-not (Test-Path $IndexHtml)) { throw "index.html not found at $IndexHtml" }
$cpArgs = @("s3", "cp", $IndexHtml, "$S3/index.html", "--content-type", "text/html", "--cache-control", "no-cache")
if ($DryRunFlag) { $cpArgs += $DryRunFlag }
aws @cpArgs
if ($LASTEXITCODE -ne 0) { throw "Failed to upload index.html" }

# 4. Invalidate CloudFront -------------------------------------------------
# "/*" refreshes EVERY object at every edge so new bundles serve immediately.
# A wildcard counts as ONE path against the free 1,000 invalidation-paths/month.
if ($DistributionId) {
  Write-Step "Invalidating CloudFront ($DistributionId) -> /*"
  if ($DryRun) {
    Write-Host "[DryRun] aws cloudfront create-invalidation --distribution-id $DistributionId --paths `"/*`"" -ForegroundColor Yellow
  }
  else {
    aws cloudfront create-invalidation --distribution-id $DistributionId --paths "/*" --query "Invalidation.{Id:Id,Status:Status}" --output json
    if ($LASTEXITCODE -ne 0) { throw "CloudFront invalidation failed" }
  }
}
else {
  Write-Host "`n(no -DistributionId; skipping CloudFront invalidation)" -ForegroundColor Yellow
}

Write-Host "`nDeploy complete. Live at https://app.pragmatic-dev.in" -ForegroundColor Green

