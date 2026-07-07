# Smoke test for the Pragmatic-dev stack (run AFTER `docker compose up`).
# Verifies the backend + tips pipeline end-to-end through nginx and directly.
#
#   ./scripts/smoke-test.ps1
#
# Exit code 0 = all checks passed.

$ErrorActionPreference = "Stop"
$fail = 0

function Test-Endpoint {
    param([string]$Name, [string]$Url, [int]$ExpectStatus = 200)
    try {
        $res = Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec 10 -UseBasicParsing
        if ($res.StatusCode -eq $ExpectStatus) {
            Write-Host ("[PASS] {0,-28} {1} ({2})" -f $Name, $Url, $res.StatusCode) -ForegroundColor Green
        } else {
            Write-Host ("[FAIL] {0,-28} {1} got {2}, want {3}" -f $Name, $Url, $res.StatusCode, $ExpectStatus) -ForegroundColor Red
            $script:fail++
        }
    } catch {
        Write-Host ("[FAIL] {0,-28} {1} -> {2}" -f $Name, $Url, $_.Exception.Message) -ForegroundColor Red
        $script:fail++
    }
}

Write-Host "`n== Backend (direct :8000) ==" -ForegroundColor Cyan
Test-Endpoint "health"          "http://localhost:8000/health"
Test-Endpoint "openapi docs"    "http://localhost:8000/docs"
Test-Endpoint "tip (may be null)" "http://localhost:8000/tip"
Test-Endpoint "liveness"        "http://localhost:8000/tip/liveness" -Method POST

Write-Host "`n== Through nginx (:80) ==" -ForegroundColor Cyan
Test-Endpoint "api health"      "http://localhost/api/health"
Test-Endpoint "api tip"         "http://localhost/api/tip"

Write-Host "`n== Tip generation (cold start) ==" -ForegroundColor Cyan
Write-Host "Pinged liveness above; waiting ~8s for the worker to generate a tip..."
Start-Sleep -Seconds 8
try {
    $tip = Invoke-RestMethod -Uri "http://localhost:8000/tip" -TimeoutSec 10
    if ($tip.tip -and $tip.tip.text) {
        Write-Host ("[PASS] tip generated: `"{0}`"" -f $tip.tip.text) -ForegroundColor Green
    } else {
        Write-Host "[WARN] no tip yet (check OPENAI_API_KEY in backend/.env & worker/.env, and worker logs)" -ForegroundColor Yellow
    }
} catch {
    Write-Host ("[FAIL] tip fetch -> {0}" -f $_.Exception.Message) -ForegroundColor Red
    $fail++
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host "All checks passed." -ForegroundColor Green
    exit 0
} else {
    Write-Host ("{0} check(s) failed." -f $fail) -ForegroundColor Red
    exit 1
}


