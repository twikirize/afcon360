<# 
.SYNOPSIS
    AFCON360 Auto-Start: Launches Flask API + Metro Bundler + Firewall + Phone App
.DESCRIPTION
    Run this script once to start everything. Keeps running in background.
    Automatically detects laptop's LAN IP (WiFi or hotspot) and uses it for all connections.
    Double-click start-afcon360.bat or run: powershell -ExecutionPolicy Bypass -File start-afcon360.ps1 -LaunchPhone
#>

param(
    [switch]$LaunchPhone,
    [switch]$NoFirewall
)

$ErrorActionPreference = "Stop"

# --- Config ---
$RepoRoot = "C:\Users\OBED\Desktop\afcon360-user-dev"
$FlaskDir = "C:\Users\OBED\Desktop\afcon360_app"
$MobileDir = "$RepoRoot\mobile\apps\user"
$FlaskHttpPort = 5000
$FlaskHttpsPort = 5443
$MetroPort = 8081

# --- Dynamic IP Detection ---
function Get-LocalLanIP {
    # Get IPv4 addresses on WiFi/Ethernet interfaces (exclude loopback, link-local, VPN)
    # Force array with @() to handle single IP case correctly
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.PrefixOrigin -in @('Dhcp', 'Manual') -and
        $_.IPAddress -notlike '127.*' -and
        $_.IPAddress -notlike '169.254.*' -and
        $_.InterfaceAlias -notlike '*Loopback*' -and
        $_.InterfaceAlias -notlike '*VPN*' -and
        $_.InterfaceAlias -notlike '*Tunnel*' -and
        $_.InterfaceAlias -notlike '*Pseudo*'
    } | Select-Object -ExpandProperty IPAddress)

    if ($ips.Count -eq 0) {
        Write-Error "No LAN IP found. Are you connected to WiFi or hotspot?"
        exit 1
    }

    # Prefer 192.168.x.x or 10.x.x.x (common LAN ranges)
    # Force array with @() to handle single match correctly
    $preferred = @($ips | Where-Object { $_ -like '192.168.*' -or $_ -like '10.*' -or $_ -like '172.1[6-9].*' -or $_ -like '172.2[0-9].*' -or $_ -like '172.3[0-1].*' })
    if ($preferred.Count -gt 0) {
        return $preferred[0]
    }
    return $ips[0]
}

$PhoneIP = Get-LocalLanIP

Write-Host "===========================================" -ForegroundColor Cyan
Write-Host "  AFCON360 AUTO-START" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host "Detected LAN IP: $PhoneIP" -ForegroundColor Green

# --- Helper: Check if process running ---
function Is-PortListening($port) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
}

function Is-ProcessRunning($name, $cmdLike) {
    Get-Process -Name $name -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like $cmdLike }
}

# --- 1. Firewall Rule ---
if (-not $NoFirewall) {
    Write-Host "`n[1/5] Checking firewall rule..." -ForegroundColor Yellow
    $rule = Get-NetFirewallRule -DisplayName "Expo Metro 8081" -ErrorAction SilentlyContinue
    if (-not $rule) {
        Write-Host "  Creating firewall rule (requires Admin)..." -ForegroundColor Yellow
        Start-Process powershell -Verb RunAs -ArgumentList "New-NetFirewallRule -DisplayName 'Expo Metro 8081' -Direction Inbound -LocalPort 8081 -Protocol TCP -Action Allow -Profile Any" -Wait
        Write-Host "  Firewall rule created." -ForegroundColor Green
    } else {
        Write-Host "  Firewall rule exists." -ForegroundColor Green
    }
}

# --- 2. Flask API ---
Write-Host "`n[2/5] Starting Flask API..." -ForegroundColor Yellow
$flaskRunning = Is-ProcessRunning "python" "*app.py*"
if ($flaskRunning) {
    Write-Host "  Flask already running (PID $($flaskRunning.Id))." -ForegroundColor Green
} else {
    Write-Host "  Launching Flask..." -ForegroundColor Yellow
    $env:AFCON360_PREVIEW_BUILD = "true"
    $env:AFCON360_RELEASE_BUILD = "false"
    $log = "$env:TEMP\afcon360_flask.log"
    $arg = '/c python app.py > "' + $log + '" 2>&1'
    Start-Process -FilePath "cmd.exe" -ArgumentList $arg -WorkingDirectory $FlaskDir -WindowStyle Hidden
    Start-Sleep -Seconds 5
    $flaskRunning = Is-ProcessRunning "python" "*app.py*"
    if ($flaskRunning) {
        Write-Host "  Flask started (PID $($flaskRunning.Id))." -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Flask may not have started. Check $log" -ForegroundColor Red
    }
}

# --- 3. Metro Bundler ---
Write-Host "`n[3/5] Starting Metro Bundler..." -ForegroundColor Yellow
$metroRunning = Is-ProcessRunning "node" "*expo*"
if ($metroRunning) {
    Write-Host "  Metro already running (PID $($metroRunning.Id))." -ForegroundColor Green
} else {
    Write-Host "  Launching Metro..." -ForegroundColor Yellow
    $env:AFCON360_PREVIEW_BUILD = "true"
    $env:AFCON360_RELEASE_BUILD = "false"
    $log = "$env:TEMP\afcon360_metro.log"
    $arg = '/c npx expo start --dev-client --host lan --port 8081 > "' + $log + '" 2>&1'
    Start-Process -FilePath "cmd.exe" -ArgumentList $arg -WorkingDirectory $MobileDir -WindowStyle Hidden
    Start-Sleep -Seconds 15
    $metroRunning = Is-ProcessRunning "node" "*expo*"
    if ($metroRunning) {
        Write-Host "  Metro started (PID $($metroRunning.Id))." -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Metro may not have started. Check $log" -ForegroundColor Red
    }
}

# --- 4. Verify Ports ---
Write-Host "`n[4/5] Verifying ports..." -ForegroundColor Yellow
$flaskHttp = Is-PortListening $FlaskHttpPort
$flaskHttps = Is-PortListening $FlaskHttpsPort
$metroPort = Is-PortListening $MetroPort
if ($flaskHttp) { Write-Host "  Flask HTTP:  LISTENING on port $FlaskHttpPort" -ForegroundColor Green } else { Write-Host "  Flask HTTP:  NOT listening on port $FlaskHttpPort" -ForegroundColor Yellow }
if ($flaskHttps) { Write-Host "  Flask HTTPS: LISTENING on port $FlaskHttpsPort" -ForegroundColor Green } else { Write-Host "  Flask HTTPS: NOT listening on port $FlaskHttpsPort" -ForegroundColor Yellow }
if ($metroPort) { Write-Host "  Metro:       LISTENING on port $MetroPort" -ForegroundColor Green } else { Write-Host "  Metro:       NOT listening on port $MetroPort" -ForegroundColor Red }

# --- 5. Launch Phone App ---
if ($LaunchPhone) {
    Write-Host "`n[5/5] Launching app on phone..." -ForegroundColor Yellow
    $adb = "C:\Users\OBED\AppData\Local\Android\Sdk\platform-tools\adb.exe"
    if (Test-Path $adb) {
        & $adb shell am force-stop space.pamoja.afcon360.user.preview
        Start-Sleep -Seconds 2
        $deepLink = "afcon360-preview://expo-development-client/?url=http%3A%2F%2F$PhoneIP%3A8081"
        & $adb shell am start -a android.intent.action.VIEW -d $deepLink
        Write-Host "  App launched on phone." -ForegroundColor Green
    } else {
        Write-Host "  ADB not found at $adb" -ForegroundColor Red
    }
}

Write-Host "`n===========================================" -ForegroundColor Cyan
Write-Host "  AFCON360 READY" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host "LAN IP:     $PhoneIP" -ForegroundColor Green
Write-Host "Flask API:  https://$PhoneIP`:$FlaskHttpsPort (HTTP on $FlaskHttpPort)" -ForegroundColor Cyan
Write-Host "Metro:      http://$PhoneIP`:$MetroPort" -ForegroundColor Cyan
Write-Host ""
Write-Host "Phone Settings:" -ForegroundColor Yellow
Write-Host "  API Base:  https://$PhoneIP`:$FlaskHttpsPort" -ForegroundColor Yellow
Write-Host "  Metro URL: http://$PhoneIP`:$MetroPort" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop all services." -ForegroundColor Gray

# Keep script alive so background processes stay running
if ($metroRunning -or $flaskRunning) {
    Write-Host "`nRunning... (Ctrl+C to exit)" -ForegroundColor Gray
    try {
        while ($true) { Start-Sleep -Seconds 10 }
    } catch {
        Write-Host "`nShutting down..." -ForegroundColor Yellow
    }
}