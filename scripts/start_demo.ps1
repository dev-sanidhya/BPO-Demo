param(
    [switch]$NoDesktop,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$repoDesktopExe = Join-Path $repoRoot "apps\console\release\win-unpacked\Aperture CX Agent.exe"
$installedDesktopExe = Join-Path $env:LOCALAPPDATA "Programs\Aperture CX Agent\Aperture CX Agent.exe"

$groqKey = [Environment]::GetEnvironmentVariable("GROQ_API_KEY", "User")
if ([string]::IsNullOrWhiteSpace($env:GROQ_API_KEY)) { $env:GROQ_API_KEY = $groqKey }
if ([string]::IsNullOrWhiteSpace($env:GROQ_API_KEY)) {
    throw "GROQ_API_KEY is missing. Add it to the Windows User environment, then open a new PowerShell window."
}

$env:AGENT_UI_PORT = if ($env:AGENT_UI_PORT) { $env:AGENT_UI_PORT } else { "18082" }
$env:PLATFORM_SIP_ENABLED = "true"
$env:PLATFORM_SIP_WS_URL = "ws://127.0.0.1:8088/ws"
$env:PLATFORM_SIP_HOST = "127.0.0.1"
$env:PLATFORM_SIP_EXTENSION = "1001"
$env:PLATFORM_SIP_PASSWORD = "changeme1001"
$env:PLATFORM_API_URL = "http://127.0.0.1:18080"

Push-Location $repoRoot
try {
    $composeArgs = @("compose", "--profile", "legacy-ui", "up", "-d")
    if ($Rebuild) { $composeArgs += "--build" }
    $composeArgs += @("postgres", "platform-api", "platform-worker", "console", "asterisk", "agent-ui")
    & docker @composeArgs
    if ($LASTEXITCODE -ne 0) { throw "Docker services did not start" }

    $deadline = (Get-Date).AddSeconds(90)
    do {
        try { $healthy = (Invoke-RestMethod "http://127.0.0.1:18080/health" -TimeoutSec 3).status -eq "ok" }
        catch { $healthy = $false }
        if (-not $healthy) { Start-Sleep -Seconds 2 }
    } while (-not $healthy -and (Get-Date) -lt $deadline)
    if (-not $healthy) { throw "Aperture API did not become healthy. Run: docker compose logs platform-api" }

    Write-Host "Aperture CX is ready." -ForegroundColor Green
    Write-Host "Operations portal: http://127.0.0.1:18081"
    Write-Host "Customer call endpoint: http://127.0.0.1:18082/?ext=1003&pass=changeme1003&assist=0&target=2101"

    if (-not $NoDesktop) {
        $desktopExe = if (Test-Path -LiteralPath $repoDesktopExe) { $repoDesktopExe } else { $installedDesktopExe }
        if (-not (Test-Path -LiteralPath $desktopExe)) {
            throw "Aperture desktop is not installed and no packaged build exists. Run the installer under apps\console\release."
        }
        Start-Process -FilePath $desktopExe -WorkingDirectory (Split-Path -Parent $desktopExe)
    }
}
finally {
    Pop-Location
}
