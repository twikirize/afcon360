[CmdletBinding()]
param(
    [ValidateSet("Auto", "Lan", "Usb")]
    [string]$ConnectionMode = "Auto",
    [string]$BackendRoot,
    [string]$MetroHost,
    [string]$DeviceSerial,
    [ValidateRange(1024, 65535)]
    [int]$MetroPort = 8081,
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 5000,
    [switch]$SkipApiStart,
    [switch]$ClearMetroCache
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$MobileRoot = Join-Path $RepoRoot "mobile"
$MetroScript = Join-Path $PSScriptRoot "start-user-metro.ps1"
$LaunchScript = Join-Path $PSScriptRoot "launch-user-dev-client.ps1"

if (-not $BackendRoot) {
    if ($env:AFCON360_BACKEND_ROOT) {
        $BackendRoot = $env:AFCON360_BACKEND_ROOT
    } else {
        $BackendRoot = Join-Path (Split-Path $RepoRoot -Parent) "afcon360_app"
    }
}
$BackendRoot = [System.IO.Path]::GetFullPath($BackendRoot)

function Find-Adb {
    $command = Get-Command "adb" -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $sdkRoots = @()
    if ($env:ANDROID_HOME) { $sdkRoots += $env:ANDROID_HOME }
    if ($env:ANDROID_SDK_ROOT) { $sdkRoots += $env:ANDROID_SDK_ROOT }
    if ($env:LOCALAPPDATA) { $sdkRoots += (Join-Path $env:LOCALAPPDATA "Android\Sdk") }
    foreach ($root in ($sdkRoots | Select-Object -Unique)) {
        $candidate = Join-Path $root "platform-tools\adb.exe"
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Find-LanAddress {
    $configs = @(Get-NetIPConfiguration -ErrorAction Stop | Where-Object {
        $_.NetAdapter -and $_.NetAdapter.Status -eq "Up" -and $_.IPv4Address -and
        $_.InterfaceAlias -notmatch "(?i)vpn|tunnel|loopback|virtualbox|vmware|wsl|bluetooth"
    })
    $candidates = @()
    foreach ($config in $configs) {
        foreach ($entry in @($config.IPv4Address)) {
            $address = [string]$entry.IPAddress
            if (-not $address -or $address -match "^(127\.|169\.254\.|0\.)") { continue }
            $score = 0
            if ($address -eq "192.168.137.1") { $score += 500 }
            elseif ($address -like "192.168.43.*") { $score += 480 }
            elseif ($address -like "172.20.10.*") { $score += 470 }
            elseif ($address -like "192.168.*") { $score += 300 }
            elseif ($address -like "10.*" -or $address -match "^172\.(1[6-9]|2[0-9]|3[01])\.") { $score += 280 }
            if ($config.IPv4DefaultGateway) { $score += 100 }
            if ($config.InterfaceAlias -match "(?i)wi-?fi|wireless") { $score += 40 }
            elseif ($config.InterfaceAlias -match "(?i)ethernet|local area connection") { $score += 20 }
            $candidates += [PSCustomObject]@{ Address = $address; Score = $score; Interface = $config.InterfaceAlias }
        }
    }
    if ($candidates.Count -eq 0) { return $null }
    return ($candidates | Sort-Object Score -Descending | Select-Object -First 1)
}

function Get-DeviceList {
    param([string]$AdbPath)
    if (-not $AdbPath) { return @() }
    $lines = @(& $AdbPath devices -l)
    if ($LASTEXITCODE -ne 0) { return @() }
    $devices = @()
    foreach ($line in $lines) {
        if ($line -match "^(\S+)\s+device(?:\s|$)") {
            $devices += [PSCustomObject]@{
                Serial = $Matches[1]
                IsNetwork = ($Matches[1] -match "^\d{1,3}(?:\.\d{1,3}){3}:\d+$" -or $line -match "tcp:")
            }
        }
    }
    return $devices
}

function Test-ApiReady {
    param([string]$Url)
    try {
        $response = Invoke-RestMethod -Uri ($Url + "/api/health/ready") -Method Get -TimeoutSec 3
        return ($response.status -eq "ready")
    } catch {
        return $false
    }
}

function Start-LocalApi {
    param([string]$Root, [string]$BindAddress, [int]$Port)
    if (-not (Test-Path (Join-Path $Root "app.py"))) {
        throw "The local Flask backend was not found at '$Root'. Set AFCON360_BACKEND_ROOT or pass -BackendRoot."
    }

    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        if ($BindAddress -eq "0.0.0.0") {
            $reachable = @($listeners | Where-Object {
                $_.LocalAddress -eq "0.0.0.0" -or $_.LocalAddress -eq "::" -or
                $_.LocalAddress -eq $script:MetroHost
            })
            if ($reachable.Count -eq 0) {
                throw "Port $Port is already occupied by a loopback-only or unrelated server. For Wi-Fi/hotspot the laptop API must listen on 0.0.0.0. Stop the old local API and rerun; no process was stopped automatically."
            }
        }
        Write-Host ("Reusing API listener on port {0} (PID(s): {1})." -f $Port, (@($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", ")) -ForegroundColor Yellow
    } else {
        $python = Join-Path $Root ".venv\Scripts\python.exe"
        if (-not (Test-Path $python)) {
            $pythonCommand = Get-Command "python" -ErrorAction SilentlyContinue
            if (-not $pythonCommand) { throw "No backend Python found. Expected $python or python on PATH." }
            $python = $pythonCommand.Source
        }

        $stdout = Join-Path $env:TEMP ("afcon360-user-api-{0}.log" -f $Port)
        $stderr = Join-Path $env:TEMP ("afcon360-user-api-{0}-error.log" -f $Port)
        $oldEnv = @{}
        $envNames = @("APP_ENV", "FLASK_ENV", "FLASK_DEBUG", "FLASK_HOST", "FLASK_PORT", "FLASK_SSL")
        foreach ($name in $envNames) { $oldEnv[$name] = [Environment]::GetEnvironmentVariable($name, "Process") }

        try {
            $env:APP_ENV = "local"
            $env:FLASK_ENV = "development"
            $env:FLASK_DEBUG = "false"
            $env:FLASK_HOST = $BindAddress
            $env:FLASK_PORT = "$Port"
            $env:FLASK_SSL = "none"
            $process = Start-Process -FilePath $python -ArgumentList @("app.py") -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
        } finally {
            foreach ($name in $envNames) {
                if ($null -eq $oldEnv[$name]) {
                    Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue
                } else {
                    Set-Item ("Env:" + $name) $oldEnv[$name]
                }
            }
        }
        Write-Host ("Started local Flask API (PID {0}); logs: {1}" -f $process.Id, $stdout) -ForegroundColor Green
    }

    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if (Test-ApiReady -Url ("http://127.0.0.1:" + $Port)) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) {
        $log = Join-Path $env:TEMP ("afcon360-user-api-{0}.log" -f $Port)
        $errorLog = Join-Path $env:TEMP ("afcon360-user-api-{0}-error.log" -f $Port)
        $tail = @()
        if (Test-Path $log) { $tail += Get-Content $log -Tail 35 }
        if (Test-Path $errorLog) { $tail += Get-Content $errorLog -Tail 35 }
        $tailText = $tail -join [Environment]::NewLine
        throw ("The local API did not pass /api/health/ready. Check the database and backend startup. Last log lines: " + $tailText)
    }
    Write-Host ("Local API readiness passed: http://127.0.0.1:{0}/api/health/ready" -f $Port) -ForegroundColor Green
}

if (-not (Test-Path $MobileRoot) -or -not (Test-Path $MetroScript) -or -not (Test-Path $LaunchScript)) {
    throw ("The User mobile workspace development helpers could not be found under " + $RepoRoot)
}

$adb = Find-Adb
$devices = Get-DeviceList -AdbPath $adb
if ($DeviceSerial) {
    if (-not ($devices | Where-Object { $_.Serial -eq $DeviceSerial })) {
        throw ("ADB device '" + $DeviceSerial + "' is not connected and authorized.")
    }
} elseif ($devices.Count -eq 1) {
    $DeviceSerial = $devices[0].Serial
} elseif ($devices.Count -gt 1) {
    throw "Multiple ADB devices are connected. Rerun with -DeviceSerial to select the intended phone."
}

if ($ConnectionMode -eq "Auto") {
    $usbDevice = @($devices | Where-Object { -not $_.IsNetwork })
    if ($usbDevice.Count -gt 0) { $ConnectionMode = "Usb" } else { $ConnectionMode = "Lan" }
}
if ($ConnectionMode -eq "Usb" -and -not $DeviceSerial) {
    throw "USB mode requires one authorized ADB device. Connect the phone by USB and approve USB debugging, or select LAN mode."
}

if ($ConnectionMode -eq "Usb") {
    $MetroHost = "127.0.0.1"
    $ApiBaseUrl = "http://127.0.0.1:" + $ApiPort
    $BindAddress = "127.0.0.1"
    $MetroConnectionMode = "Usb"
} else {
    $selected = $null
    if ($MetroHost) {
        $selected = [PSCustomObject]@{ Address = $MetroHost; Interface = "manually supplied adapter" }
    } else {
        $selected = Find-LanAddress
    }
    if (-not $selected) { throw "No active LAN/hotspot IPv4 address was found. Connect Wi-Fi/hotspot or pass -MetroHost." }
    $MetroHost = $selected.Address
    $ApiBaseUrl = "http://" + $MetroHost + ":" + $ApiPort
    $BindAddress = "0.0.0.0"
    $MetroConnectionMode = "Lan"
    Write-Host ("Selected laptop network: {0} ({1})" -f $MetroHost, $selected.Interface) -ForegroundColor Cyan
}

Write-Host ""
Write-Host "AFCON360 USER APP - DEVELOPMENT SESSION" -ForegroundColor Cyan
Write-Host ("Connection mode : " + $ConnectionMode)
Write-Host ("API base         : " + $ApiBaseUrl)
Write-Host ("Metro address    : http://" + $MetroHost + ":" + $MetroPort)
Write-Host ("Backend folder   : " + $BackendRoot)
Write-Host "Native rebuild   : not performed by this script"
Write-Host ""

if (-not $SkipApiStart) {
    Start-LocalApi -Root $BackendRoot -BindAddress $BindAddress -Port $ApiPort
} elseif (-not (Test-ApiReady -Url ("http://127.0.0.1:" + $ApiPort))) {
    throw ("The existing local API is not ready at http://127.0.0.1:" + $ApiPort + ".")
}

$metroListeners = @(Get-NetTCPConnection -LocalPort $MetroPort -State Listen -ErrorAction SilentlyContinue)
if ($metroListeners.Count -gt 0) {
    $pids = @($metroListeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    throw ("Metro port " + $MetroPort + " is already in use (PID(s): " + $pids + "). Stop the old Metro process and rerun so the correct network/API settings are loaded.")
}

$quote = [char]34
$metroArgs = "-NoExit -ExecutionPolicy Bypass -File " + $quote + $MetroScript + $quote +
    " -Port " + $MetroPort + " -ConnectionMode " + $MetroConnectionMode +
    " -ApiBaseUrl " + $quote + $ApiBaseUrl + $quote
if ($ClearMetroCache) { $metroArgs += " -ClearCache" }
Start-Process -FilePath "powershell.exe" -ArgumentList $metroArgs | Out-Null
Write-Host "Metro is starting in a separate PowerShell window..." -ForegroundColor Green

$metroReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    $listener = Get-NetTCPConnection -LocalPort $MetroPort -State Listen -ErrorAction SilentlyContinue
    if ($listener) { $metroReady = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $metroReady) {
    throw ("Metro did not start listening on port " + $MetroPort + ". Check the separate Metro PowerShell window.")
}

if ($adb -and $DeviceSerial) {
    & $LaunchScript -ConnectionMode $ConnectionMode -MetroHost $MetroHost -Port $MetroPort -ApiPort $ApiPort -DeviceSerial $DeviceSerial
    if ($LASTEXITCODE -ne 0) { throw "The development client launch helper failed." }
} else {
    Write-Host "No ADB device selected. Scan the QR/development-client URL shown in the Metro window on the phone." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "DEVELOPMENT SESSION READY" -ForegroundColor Green
Write-Host ("API:   " + $ApiBaseUrl)
Write-Host ("Metro: http://" + $MetroHost + ":" + $MetroPort)
Write-Host "Use the app's Connection settings -> Use server for this development session to switch its saved API origin."
Write-Host ("For LAN mode, ensure Windows Firewall allows private-network TCP ports " + $ApiPort + " and " + $MetroPort + ".")
Write-Host "No native build or APK installation was performed."
