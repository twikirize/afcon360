[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8081,
    [ValidatePattern('^https?://')]
    [string]$ApiBaseUrl = "https://www.pamoja.space",
    [switch]$ClearCache
)

$ErrorActionPreference = "Stop"
$MobileRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$UserAppRoot = Join-Path $MobileRoot "apps\user"

if (-not (Test-Path (Join-Path $MobileRoot "pnpm-workspace.yaml"))) {
    throw "The mobile pnpm workspace was not found at: $MobileRoot"
}
if (-not (Test-Path (Join-Path $UserAppRoot "app.config.ts"))) {
    throw "The User App was not found at: $UserAppRoot"
}

$Pnpm = Get-Command "pnpm" -ErrorAction SilentlyContinue
if (-not $Pnpm) {
    throw "pnpm was not found on PATH. Install the workspace-pinned pnpm version and reopen PowerShell."
}
$Node = Get-Command "node" -ErrorAction SilentlyContinue
if (-not $Node) { throw "Node.js was not found on PATH." }

$parsedApi = $null
if (-not [Uri]::TryCreate($ApiBaseUrl, [UriKind]::Absolute, [ref]$parsedApi) -or
    $parsedApi.Scheme -notin @("http", "https")) {
    throw "ApiBaseUrl must be an absolute HTTP or HTTPS URL."
}

$existingListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existingListener) {
    $owners = @($existingListener | Select-Object -ExpandProperty OwningProcess -Unique)
    throw "Port $Port is already in use by process ID(s): $($owners -join ', '). Stop the old Metro server or choose another -Port."
}

$env:AFCON360_PREVIEW_BUILD = "true"
$env:AFCON360_RELEASE_BUILD = "false"
$env:AFCON360_DEVELOPMENT_CLIENT = "true"
$env:AFCON360_UPDATE_CHANNEL = "user-development-client"
$env:EXPO_PUBLIC_API_BASE_URL = $ApiBaseUrl.TrimEnd("/")

Write-Host ""
Write-Host "AFCON360 USER APP - METRO DEVELOPMENT" -ForegroundColor Cyan
Write-Host "Mobile workspace : $MobileRoot"
Write-Host "User application : $UserAppRoot"
Write-Host "Node             : $(& $Node.Source --version)"
Write-Host "pnpm             : $(& $Pnpm.Source --version)"
Write-Host "API base          : $env:EXPO_PUBLIC_API_BASE_URL"
Write-Host "Update channel    : user-development-client"
Write-Host "Dev-client scheme : afcon360-preview-dev"
Write-Host "Port              : $Port"
Write-Host ""
Write-Host "This starts Metro only. It does not compile or reinstall the Android app."
Write-Host "JavaScript and TypeScript changes can refresh through the installed dev client."
Write-Host "Native dependency or native configuration changes still require a new APK."
Write-Host ""

$ExpoArgs = @("--filter", "@afcon360/user-app", "exec", "expo", "start", "--dev-client", "--host", "lan", "--port", "$Port")
if ($ClearCache) { $ExpoArgs += "--clear" }

Push-Location $MobileRoot
try {
    & $Pnpm.Source @ExpoArgs
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
if ($ExitCode -ne 0) { throw "Expo Metro exited with code $ExitCode." }
