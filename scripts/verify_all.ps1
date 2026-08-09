param(
    [switch]$IncludePackage
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    python scripts\verify_voice_fixture.py
    if ($LASTEXITCODE -ne 0) { throw "Voice fixture verification failed" }

    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Compose validation failed" }
    docker compose build platform-api platform-worker console
    if ($LASTEXITCODE -ne 0) { throw "Container build failed" }
    docker run --rm -v "${repoRoot}\services\platform-api\tests:/app/tests:ro" bpo-demo-platform-api pytest -q
    if ($LASTEXITCODE -ne 0) { throw "API tests failed" }
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw "Default stack startup failed" }

    $health = Invoke-RestMethod http://127.0.0.1:18080/health
    if ($health.status -ne "ok") { throw "API health check failed" }

    Push-Location apps\console
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Console build failed" }
        npm run test:e2e:web
        if ($LASTEXITCODE -ne 0) { throw "Web E2E failed" }
        npm run test:e2e:electron
        if ($LASTEXITCODE -ne 0) { throw "Electron E2E failed" }
        if ($IncludePackage) {
            npm run electron:dist:win
            if ($LASTEXITCODE -ne 0) { throw "Windows packaging failed" }
            npm run test:e2e:packaged
            if ($LASTEXITCODE -ne 0) { throw "Packaged application E2E failed" }
        }
    }
    finally {
        Pop-Location
    }

    Write-Host "Aperture CX acceptance verification passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
