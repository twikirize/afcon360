<#
.SYNOPSIS
    Starts all AFCON360 development services and connects the phone app.
.DESCRIPTION
    1. Metro Listener (port 8082, all interfaces) - receives wake requests
    2. Metro Manager - watches triggers and starts Metro
    3. Flask API (port 5000) - backend API for the app
    4. Connects the phone:
       - Lan mode (default): over Wi-Fi using the laptop LAN IP; USB only used to launch the app
       - Usb mode: adb reverse tunnels over the USB cable
.NOTES
    Lan mode requires the phone and laptop on the same Wi-Fi network and Windows
    Firewall inbound allowances for TCP 8081, 8082, 5000. When this script is run
    as Administrator it adds the missing rules; otherwise it prints the commands.

    Use -PhoneStart (alias -NoMetro) to leave Metro stopped and let the phone's
    Developer screen wake it (Account -> Developer -> Wake Metro on Laptop).
#>
[CmdletBinding()]
param(
    [ValidateSet("Lan", "Usb")]
    [string]$Mode = "Lan",
    [string]$LanIp,
    [switch]$Restart,
    [switch]$NoLaunch,
    [switch]$ClearCache,
    [switch]$NoFlask,
    [Alias("NoMetro")]
    [switch]$PhoneStart
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$AfconRoot = "C:\Users\OBED\Desktop\afcon360_app"
$PhoneId = "HQ61BR0F03"
$Adb = "C:\Users\OBED\AppData\Local\Android\Sdk\platform-tools\adb.exe"
$AppPackage = "space.pamoja.afcon360.user.preview.dev"
$AppScheme = "afcon360-preview-dev"

function Get-LanIp {
    if ($LanIp) { return $LanIp }
    # Windows Mobile hotspot default address
    $hotspot = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -eq "192.168.137.1" } | Select-Object -First 1
    if ($hotspot) { return $hotspot.IPAddress }
    # Wi-Fi interface (shared Wi-Fi or phone hotspot)
    $wifi = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -like "Wi-Fi*" -and $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Sort-Object InterfaceMetric | Select-Object -First 1
    if ($wifi) { return $wifi.IPAddress }
    # Default route fallback
    $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric | Select-Object -First 1
    if ($route) {
        $ip = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.ifIndex -ErrorAction SilentlyContinue |
            Select-Object -First 1).IPAddress
        if ($ip) { return $ip }
    }
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Sort-Object InterfaceMetric | Select-Object -First 1).IPAddress
    if (-not $ip) { throw "Could not detect the laptop LAN IPv4 address" }
    return $ip
}

function Ensure-FirewallRules {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $rules = @(
        @{ Name = "AFCON360 Metro 8081"; Port = 8081 },
        @{ Name = "AFCON360 Listener 8082"; Port = 8082 },
        @{ Name = "AFCON360 API 5000"; Port = 5000 }
    )
    foreach ($rule in $rules) {
        $existing = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
        if ($isAdmin) {
            if ($existing) {
                Set-NetFirewallRule -DisplayName $rule.Name -Profile Private,Public -Enabled True `
                    -Action Allow -RemoteAddress LocalSubnet | Out-Null
            } else {
                New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound -Action Allow `
                    -Protocol TCP -LocalPort $rule.Port -Profile Private,Public `
                    -RemoteAddress LocalSubnet | Out-Null
                Write-Host "Firewall rule added: $($rule.Name) (TCP $($rule.Port), LocalSubnet)" -ForegroundColor Green
            }
        } elseif ($existing) {
            if (([string]$existing.Profile) -notmatch "Public|Any") {
                Write-Warning "Firewall rule '$($rule.Name)' lacks the Public profile; hotspot networks may be blocked."
                Write-Warning "Run PowerShell as Administrator once:"
                Write-Warning "  Set-NetFirewallRule -DisplayName '$($rule.Name)' -Profile Private,Public -Enabled True -Action Allow -RemoteAddress LocalSubnet"
            }
        } else {
            Write-Warning "Missing firewall rule '$($rule.Name)' for TCP $($rule.Port); the phone may be blocked."
            Write-Warning "Run PowerShell as Administrator once:"
            Write-Warning "  New-NetFirewallRule -DisplayName '$($rule.Name)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $($rule.Port) -Profile Private,Public -RemoteAddress LocalSubnet"
        }
    }
}

function Test-HttpStatus([string]$Url, [int]$Seconds = 3) {
    $code = & curl.exe -s -m $Seconds -o NUL -w "%{http_code}" $Url 2>$null
    return ($code -join "")
}

$LanIp = Get-LanIp
if ($Mode -eq "Lan") {
    $ApiBaseUrl = "http://${LanIp}:5000"
    $MetroUrl = "http://${LanIp}:8081"
} else {
    $ApiBaseUrl = "http://127.0.0.1:5000"
    $MetroUrl = "http://127.0.0.1:8081"
}

Write-Host "=== AFCON360 DEV STACK STARTUP ===" -ForegroundColor Cyan
Write-Host "Repo root: $RepoRoot"
Write-Host "Mode:      $Mode"
if ($LanIp) {
    Write-Host "LAN IP:    $LanIp"
    $candidates = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        ForEach-Object { "$($_.InterfaceAlias)=$($_.IPAddress)" }
    Write-Host "IPv4:      $($candidates -join '; ')"
    $profile = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($profile) { Write-Host "Network:   $($profile.Name) ($($profile.NetworkCategory))" }
}
Write-Host "Phone:     $PhoneId"
Write-Host ""

if ($Restart) {
    Write-Host "Stopping existing AFCON360 dev services..." -ForegroundColor Yellow
    $killPattern = 'metro_manager\.py|metro_listener\.py|start-user-metro\.ps1|expo start'
    if (-not $NoFlask) { $killPattern += '|app\.py' }
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'powershell.exe' OR Name = 'node.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match $killPattern } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    $ports = @(8081, 8082)
    if (-not $NoFlask) { $ports += 5000 }
    foreach ($port in $ports) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    }
    Start-Sleep -Seconds 2
}

# 0. Clear stale wake artifacts so an old trigger cannot start Metro inadvertently
Remove-Item -Force -ErrorAction SilentlyContinue `
    (Join-Path $RepoRoot "metro_trigger.json"), `
    (Join-Path $RepoRoot "metro_status.json")

# 1. Start Metro Listener
Write-Host "Starting Metro Listener (port 8082)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$RepoRoot'; python metro_listener.py"

# 2. Start Metro Manager (mode and API URL are passed via environment)
Write-Host "Starting Metro Manager ($Mode mode)..." -ForegroundColor Yellow
$managerCmd = "cd '$RepoRoot'; `$env:AFCON_METRO_CONNECTION_MODE='$Mode'; `$env:AFCON_API_BASE_URL='$ApiBaseUrl'; `$env:AFCON_METRO_CLEAR_CACHE='$([int]$ClearCache.IsPresent)'; python metro_manager.py"
Start-Process powershell -ArgumentList '-NoExit', '-Command', $managerCmd

# 3. Start Flask API on the phone-preview environment (HTTP 0.0.0.0:5000)
if ($NoFlask) {
    Write-Host "Using the Flask API already running on port 5000 (PyCharm)..." -ForegroundColor Yellow
} else {
    Write-Host "Starting Flask API (port 5000)..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$AfconRoot'; `$env:APP_ENV='phone-preview'; .venv\Scripts\python.exe app.py"
}

# Wait for Flask API to be ready
Write-Host "Waiting for Flask API..." -ForegroundColor Cyan
$flaskReady = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/health/ready" -Method GET `
            -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { $flaskReady = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if (-not $flaskReady) { throw "Flask API did not become ready. Start app.py with APP_ENV=phone-preview, or omit -NoFlask." }
Write-Host "Flask API ready" -ForegroundColor Green

# 4. Networking
$devices = & $Adb devices 2>$null
$deviceOnline = (($devices -join "`n") -match ([regex]::Escape($PhoneId) + "\s+device"))

if ($Mode -eq "Lan") {
    Ensure-FirewallRules

    # Prove Flask is bound on the LAN interface when the phone is online
    $lanFlask = Test-HttpStatus "http://${LanIp}:5000/api/health/ready"
    if ($lanFlask -ne "200") {
        Write-Warning "Flask did not answer on $ApiBaseUrl (got '$lanFlask')."
    } else {
        Write-Host "Flask reachable on LAN: $ApiBaseUrl" -ForegroundColor Green
    }

    # USB is only a convenience for launching; connectivity is Wi-Fi.
    if ($deviceOnline) {
        Write-Host "Removing adb reverse tunnels (LAN mode does not use them)..." -ForegroundColor Yellow
        & $Adb -s $PhoneId reverse --remove-all | Out-Null
        $wifiOn = (& $Adb -s $PhoneId shell settings get global wifi_on).Trim()
        $wlan = & $Adb -s $PhoneId shell ip -f inet addr show wlan0 2>$null
        if ($wifiOn -ne "1" -or -not (($wlan -join "`n") -match "inet ")) {
            Write-Warning "Phone Wi-Fi is OFF or not connected. Enable Wi-Fi and join the same network as the laptop before unplugging USB."
        } else {
            $phoneIp = ([regex]::Match(($wlan -join "`n"), "inet (\d+\.\d+\.\d+\.\d+)")).Groups[1].Value
            if ($phoneIp) {
                $phoneSubnet = ($phoneIp -split "\.")[0..2] -join "."
                $lanSubnet = ($LanIp -split "\.")[0..2] -join "."
                if ($phoneSubnet -ne $lanSubnet) {
                    Write-Warning "Phone IP $phoneIp is not on the laptop subnet $lanSubnet.0/24; cross-network access may be blocked."
                } else {
                    Write-Host "Phone on same subnet: $phoneIp" -ForegroundColor Green
                }
            }
        }
    } else {
        Write-Warning "Phone not connected via USB. Connectivity is Wi-Fi only; open the app on the phone."
    }
} else {
    Write-Host "Setting up ADB reverse tunnels..." -ForegroundColor Yellow
    if (-not $deviceOnline) { throw "USB mode requires the phone connected with USB debugging authorized" }
    & $Adb -s $PhoneId reverse "tcp:8081" "tcp:8081"
    if ($LASTEXITCODE -ne 0) { throw "ADB reverse 8081 failed" }
    & $Adb -s $PhoneId reverse "tcp:5000" "tcp:5000"
    if ($LASTEXITCODE -ne 0) { throw "ADB reverse 5000 failed" }
    & $Adb -s $PhoneId reverse "tcp:8082" "tcp:8082"
    if ($LASTEXITCODE -ne 0) { throw "ADB reverse 8082 failed" }
}

# 5. Metro: either start it here (default) or wait for the phone (phone-start)
$launched = $false
if ($PhoneStart) {
    $phoneListener = if ($Mode -eq "Lan" -and $LanIp) { "http://${LanIp}:8082" } else { "http://127.0.0.1:8082 (USB reverse)" }
    Write-Host "Phone-start mode: Metro is not started by this launcher." -ForegroundColor Cyan
    Write-Host "Waiting for the Metro Listener..." -ForegroundColor Cyan
    $listenerReady = $false
    for ($i = 0; $i -lt 20; $i++) {
        try {
            $null = Invoke-WebRequest -Uri "http://127.0.0.1:8082/health" -Method GET `
                -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            $listenerReady = $true
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $listenerReady) { throw "Metro listener did not start on port 8082" }
    Write-Host "Listener ready: $phoneListener" -ForegroundColor Green
    Write-Host "On the phone: Account -> Developer -> Wake Metro on Laptop." -ForegroundColor Yellow
    Write-Host "Set Laptop IP (for auto-wake) to $(if ($Mode -eq 'Lan' -and $LanIp) { $LanIp } else { '127.0.0.1' }), then tap Save & Connect to Metro." -ForegroundColor Yellow
    Write-Host "Metro will start on the laptop when the phone calls /wake: $MetroUrl" -ForegroundColor Yellow
    Write-Host "Note: the app must already be open (or have a cached/embedded bundle) to wake Metro." -ForegroundColor Gray
} else {
# 5. Wake Metro via listener
Write-Host "Waking Metro..." -ForegroundColor Yellow
$wakeOk = $false
$wakeBody = '{"clientId":"start-all","timestamp":' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + '}'
for ($attempt = 0; $attempt -lt 5; $attempt++) {
    try {
        $wakeResp = Invoke-WebRequest -Uri "http://127.0.0.1:8082/wake" -Method POST `
            -Headers @{ "Content-Type" = "application/json" } `
            -Body $wakeBody -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
        Write-Host "Metro wake triggered: $($wakeResp.Content)" -ForegroundColor Green
        $wakeOk = $true
        break
    } catch {
        Write-Host "Metro wake failed (attempt $($attempt + 1)/5): $_" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
}
if (-not $wakeOk) { throw "Metro wake request failed" }

# 6. Poll Metro health until running
Write-Host "Waiting for Metro to start..." -ForegroundColor Cyan
$metroReady = $false
$consecutiveFailures = 0
for ($i = 0; $i -lt 60; $i++) {
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:8082/health" -Method GET `
            -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        $data = $health.Content | ConvertFrom-Json
        $consecutiveFailures = 0
        if ($data.status -eq "running") {
            $metroReady = $true
            Write-Host "Metro running on port $($data.port)" -ForegroundColor Green
            break
        }
        if ($data.status -eq "error") {
            throw "Metro manager error: $($data.message)"
        }
        Write-Host "Metro status: $($data.status) - waiting..." -ForegroundColor Cyan
    } catch {
        $consecutiveFailures++
        Write-Host "Health check failed ($consecutiveFailures), retrying..." -ForegroundColor Yellow
        if ($consecutiveFailures -ge 12) {
            throw "Metro listener stopped responding. Check metro_status.json, metro_stdout.log and metro_stderr.log."
        }
    }
    Start-Sleep -Seconds 2
}
if (-not $metroReady) { throw "Metro did not become ready in time" }

# 6b. Wait until Metro actually serves bundles on the configured address
Write-Host "Waiting for Metro HTTP status..." -ForegroundColor Cyan
$metroHttpReady = $false
for ($i = 0; $i -lt 90; $i++) {
    $statusText = & curl.exe -s -m 3 "$MetroUrl/status" 2>$null
    if ((($statusText -join "`n") -match "packager-status:running")) {
        $metroHttpReady = $true
        break
    }
    Start-Sleep -Seconds 2
}
if (-not $metroHttpReady) { throw "Metro HTTP status did not become ready on $MetroUrl" }
Write-Host "Metro HTTP status ready on $MetroUrl" -ForegroundColor Green

# 7. Launch the app (USB used only to trigger the launch when available)
$EncodedUrl = [Uri]::EscapeDataString($MetroUrl)
$DeepLink = $AppScheme + "://expo-development-client/?url=" + $EncodedUrl
$launched = $false
if ($NoLaunch) {
    Write-Host "Skipping app launch (-NoLaunch). Metro URL: $MetroUrl" -ForegroundColor Yellow
} elseif ($deviceOnline) {
    Write-Host "Launching app with Metro URL $MetroUrl..." -ForegroundColor Yellow
    & $Adb -s $PhoneId shell am force-stop $AppPackage
    Start-Sleep -Seconds 2
    & $Adb -s $PhoneId shell am start -a android.intent.action.VIEW -d $DeepLink -p $AppPackage
    if ($LASTEXITCODE -ne 0) { throw "Failed to launch app on phone" }
    $launched = $true
} else {
    Write-Host "Open the AFCON360 app on the phone (Wi-Fi)." -ForegroundColor Yellow
    Write-Host "If the dev launcher appears, choose 'Fetch development servers' or connect to:" -ForegroundColor Yellow
    Write-Host "  $MetroUrl" -ForegroundColor Yellow
}
}

Write-Host ""
Write-Host "=== ALL SERVICES STARTED ===" -ForegroundColor Green
Write-Host "Mode           : $Mode"
$listenerUrl = if ($Mode -eq "Lan" -and $LanIp) { "http://${LanIp}:8082" } else { "http://127.0.0.1:8082" }
if ($Mode -eq "Lan" -and $LanIp) { Write-Host "LAN IP         : $LanIp" }
Write-Host "Metro Listener : $listenerUrl (wake endpoint)"
Write-Host "Metro Manager  : watches trigger file, starts Metro"
Write-Host "Flask API      : $ApiBaseUrl$(if ($NoFlask) { ' (PyCharm)' } else { '' })"
if ($PhoneStart) {
    Write-Host "Metro Bundler  : $MetroUrl (starts when the phone wakes it)"
    Write-Host "Phone app      : open it and tap Wake Metro on Laptop"
    Write-Host "Phone action   : Account -> Developer -> Wake Metro on Laptop -> Save & Connect"
} else {
    Write-Host "Metro Bundler  : $MetroUrl"
    if ($launched) {
        Write-Host "Phone app      : launched against $MetroUrl"
    } elseif ($NoLaunch) {
        Write-Host "Phone app      : not launched (-NoLaunch)"
    } else {
        Write-Host "Phone app      : not launched (no USB device); open it manually"
    }
}
Write-Host ""
if ($Mode -eq "Lan") {
    Write-Host "Lan mode auto-detects the laptop IP (phone hotspot, laptop hotspot, or shared Wi-Fi)." -ForegroundColor Gray
    Write-Host "USB can be unplugged once the app is open. Use -Restart after a network/IP change." -ForegroundColor Gray
} else {
    Write-Host "Usb mode: keep the cable connected. Use -Mode Lan for Wi-Fi/hotspot connectivity." -ForegroundColor Gray
}
if ($PhoneStart) {
    Write-Host "Phone-start mode: Metro is started by the phone, not by this window." -ForegroundColor Gray
    Write-Host "The listener stays up; reopen the app and tap Wake Metro on Laptop after a network change." -ForegroundColor Gray
}
Write-Host "Keep the Metro/Flask windows open. Rerun this launcher (it restarts safely) after a network change." -ForegroundColor Gray
Read-Host "Press Enter to exit"
