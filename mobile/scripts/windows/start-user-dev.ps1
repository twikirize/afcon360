[CmdletBinding()]
param(
    [ValidateSet("Auto", "Lan", "Usb")]
    [string]$ConnectionMode = "Auto",
    [string]$BackendRoot,
    [string]$MetroHost,
    [string]$DeviceSerial,
    [ValidateRange(1024, 65535)]
    [int]$MetroPort = 8081,
    [switch]$SkipApiStart,
    [switch]$ClearMetroCache
)

$ErrorActionPreference = "Stop"
$ApiPort = 5000
$PackageId = "space.pamoja.afcon360.user.preview.dev"

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

if (-not (Test-Path (Join-Path $MobileRoot "pnpm-workspace.yaml"))) {
    throw ("Mobile workspace not found: " + $MobileRoot)
}
if (-not (Test-Path $MetroScript) -or -not (Test-Path $LaunchScript)) {
    throw "User App Windows helper scripts are missing."
}

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

function Get-DeviceList {
    param([string]$AdbPath)

    if (-not $AdbPath) { return @() }
    $lines = @(& $AdbPath devices -l)
    if ($LASTEXITCODE -ne 0) {
        throw "Android Debug Bridge could not list connected devices."
    }

    $devices = @()
    foreach ($line in $lines) {
        if ($line -match "^(\S+)\s+device(?:\s|$)") {
            $serial = $Matches[1]
            $devices += [PSCustomObject]@{
                Serial = $serial
                IsNetwork = (
                    $serial -match "^\d{1,3}(?:\.\d{1,3}){3}:\d+$" -or
                    $line -match "tcp:"
                )
            }
        }
    }
    return $devices
}

function Find-LanAddress {
    $configs = @(Get-NetIPConfiguration -ErrorAction Stop | Where-Object {
        $_.NetAdapter -and
        $_.NetAdapter.Status -eq "Up" -and
        $_.IPv4Address -and
        $_.InterfaceAlias -notmatch "(?i)vpn|tunnel|loopback|virtualbox|vmware|wsl|bluetooth"
    })

    $candidates = @()
    foreach ($config in $configs) {
        foreach ($entry in @($config.IPv4Address)) {
            $address = [string]$entry.IPAddress
            if (-not $address -or $address -match "^(127\.|169\.254\.|0\.)") {
                continue
            }

            $score = 0
            if ($address -eq "192.168.137.1") { $score += 500 }
            elseif ($address -like "192.168.43.*") { $score += 480 }
            elseif ($address -like "172.20.10.*") { $score += 470 }
            elseif ($address -like "192.168.*") { $score += 300 }
            elseif ($address -like "10.*" -or $address -match "^172\.(1[6-9]|2[0-9]|3[01])\.") { $score += 280 }

            if ($config.IPv4DefaultGateway) { $score += 100 }
            if ($config.InterfaceAlias -match "(?i)wi-?fi|wireless") { $score += 40 }
            elseif ($config.InterfaceAlias -match "(?i)ethernet|local area connection") { $score += 20 }

            $candidates += [PSCustomObject]@{
                Address = $address
                Score = $score
                Interface = $config.InterfaceAlias
            }
        }
    }

    if ($candidates.Count -eq 0) { return $null }
    return ($candidates | Sort-Object Score -Descending | Select-Object -First 1)
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
    param(
        [string]$Root,
        [string]$BindAddress,
        [string]$ExpectedLanAddress,
        [int]$Port
    )

    if (-not (Test-Path (Join-Path $Root "app.py"))) {
        throw ("Local Flask backend was not found at " + $Root + ". Set AFCON360_BACKEND_ROOT or use -BackendRoot.")
    }

    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    $pidFile = Join-Path $env:TEMP ("afcon360-user-api-{0}.pid" -f $Port)

    if ($listeners.Count -gt 0) {
        $managedPid = $null
        if (Test-Path $pidFile) {
            $pidText = [string](Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue)
            $pidText = $pidText.Trim()
            if ($pidText -match "^\d+$") {
                $managedPid = [int]$pidText
            }
        }

        $managedListeners = @($listeners | Where-Object { $_.OwningProcess -eq $managedPid })
        $expectedAddresses = @("127.0.0.1", "::1")
        if ($BindAddress -eq "0.0.0.0") {
            $expectedAddresses = @("0.0.0.0", "::", $ExpectedLanAddress)
        }

        $matchingBind = @($managedListeners | Where-Object {
            $expectedAddresses -contains $_.LocalAddress
        })
        if ($matchingBind.Count -eq 0) {
            $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
            throw ("API port {0} is occupied by an unmanaged or differently-bound process (PID {1}). No process was stopped. Stop it manually, or use -SkipApiStart only after verifying FLASK_DEBUG=false and the correct bind." -f $Port, $owners)
        }

        Write-Host ("Reusing the API process started by this helper (PID {0})." -f $managedPid) -ForegroundColor Yellow
    } else {
        $python = Join-Path $Root ".venv\Scripts\python.exe"
        if (-not (Test-Path $python)) {
            $pythonCommand = Get-Command "python" -ErrorAction SilentlyContinue
            if (-not $pythonCommand) {
                throw "Python was not found. Expected the backend .venv or python on PATH."
            }
            $python = $pythonCommand.Source
        }

        $stdout = Join-Path $env:TEMP ("afcon360-user-api-{0}.log" -f $Port)
        $stderr = Join-Path $env:TEMP ("afcon360-user-api-{0}-error.log" -f $Port)
        $environmentNames = @("APP_ENV", "FLASK_ENV", "FLASK_DEBUG", "FLASK_HOST", "FLASK_PORT", "FLASK_SSL")
        $oldEnvironment = @{}
        foreach ($name in $environmentNames) {
            $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        }

        try {
            $env:APP_ENV = "local"
            $env:FLASK_ENV = "development"
            $env:FLASK_DEBUG = "false"
            $env:FLASK_HOST = $BindAddress
            $env:FLASK_PORT = "$Port"
            $env:FLASK_SSL = "none"

            $process = Start-Process -FilePath $python -ArgumentList "app.py" -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
        } finally {
            foreach ($name in $environmentNames) {
                if ($null -eq $oldEnvironment[$name]) {
                    Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue
                } else {
                    Set-Item ("Env:" + $name) $oldEnvironment[$name]
                }
            }
        }

        Set-Content -LiteralPath $pidFile -Value $process.Id -NoNewline
        Write-Host ("Started local Flask API (PID {0}); logs: {1}" -f $process.Id, $stdout) -ForegroundColor Green
    }

    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if (Test-ApiReady -Url ("http://127.0.0.1:" + $Port)) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 2
    }

    if (-not $ready) {
        $stdout = Join-Path $env:TEMP ("afcon360-user-api-{0}.log" -f $Port)
        $stderr = Join-Path $env:TEMP ("afcon360-user-api-{0}-error.log" -f $Port)
        $tail = @()
        if (Test-Path $stdout) { $tail += Get-Content $stdout -Tail 35 }
        if (Test-Path $stderr) { $tail += Get-Content $stderr -Tail 35 }
        throw ("Local API did not pass /api/health/ready. Check database readiness. Last log lines: " + ($tail -join [Environment]::NewLine))
    }

    Write-Host ("Local API database readiness passed on port {0}." -f $Port) -ForegroundColor Green
}

$adb = Find-Adb
$devices = Get-DeviceList -AdbPath $adb
$deviceWasExplicit = -not [string]::IsNullOrWhiteSpace($DeviceSerial)

if ($DeviceSerial) {
    if (-not ($devices | Where-Object { $_.Serial -eq $DeviceSerial })) {
        throw ("ADB device {0} is not connected and authorized." -f $DeviceSerial)
    }
} elseif ($devices.Count -eq 1) {
    $DeviceSerial = $devices[0].Serial
} elseif ($devices.Count -gt 1) {
    throw "Multiple ADB devices are connected. Rerun with -DeviceSerial to select the intended phone."
}

$deviceHasDevClient = $false
if ($adb -and $DeviceSerial) {
    $packagePath = @(& $adb -s $DeviceSerial shell pm path $PackageId 2>$null)
    $deviceHasDevClient = ($LASTEXITCODE -eq 0 -and ($packagePath -match "package:"))
}

if ($ConnectionMode -eq "Auto") {
    $usbDevices = @($devices | Where-Object { -not $_.IsNetwork })
    $selectedIsUsb = ($DeviceSerial -and @($usbDevices | Where-Object { $_.Serial -eq $DeviceSerial }).Count -gt 0)

    if ($selectedIsUsb -and $deviceHasDevClient) {
        $ConnectionMode = "Usb"
    } elseif ($selectedIsUsb -and $deviceWasExplicit) {
        throw "The selected USB device does not have the .preview.dev APK installed. Install it first, or choose LAN mode for QR launch."
    } else {
        if ($selectedIsUsb -and -not $deviceHasDevClient) {
            Write-Warning "USB debugging is connected but the .preview.dev APK is not installed. Auto will use Wi-Fi/hotspot and the Metro QR flow."
            $DeviceSerial = $null
        }
        $ConnectionMode = "Lan"
    }
}

if ($ConnectionMode -eq "Usb") {
    if (-not $DeviceSerial) {
        throw "USB mode requires one authorized ADB device."
    }
    if (-not $deviceHasDevClient) {
        throw "The selected phone does not have the .preview.dev development APK installed."
    }
} elseif ($DeviceSerial -and -not $deviceHasDevClient) {
    if ($deviceWasExplicit) {
        throw "The selected ADB device does not have the .preview.dev APK installed."
    }
    Write-Warning "The connected ADB device does not have the .preview.dev APK. Metro will display a QR code for manual launch."
    $DeviceSerial = $null
}

if ($ConnectionMode -eq "Usb") {
    $MetroHost = "127.0.0.1"
    $ApiBaseUrl = "http://127.0.0.1:5000"
    $BindAddress = "127.0.0.1"
    $MetroConnectionMode = "Usb"
} else {
    $selectedNetwork = $null
    if ($MetroHost) {
        $ip = $null
        if (-not [System.Net.IPAddress]::TryParse($MetroHost, [ref]$ip) -or
            $ip.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
            throw "-MetroHost must be a laptop IPv4 address."
        }
        $selectedNetwork = [PSCustomObject]@{ Address = $MetroHost; Interface = "manual adapter selection" }
    } else {
        $selectedNetwork = Find-LanAddress
    }

    if (-not $selectedNetwork) {
        throw "No active laptop Wi-Fi/hotspot IPv4 address was found. Connect a network, use USB, or supply -MetroHost."
    }

    $MetroHost = $selectedNetwork.Address
    $ApiBaseUrl = "http://" + $MetroHost + ":5000"
    $BindAddress = "0.0.0.0"
    $MetroConnectionMode = "Lan"
    Write-Host ("Laptop network selected: {0} ({1})" -f $MetroHost, $selectedNetwork.Interface) -ForegroundColor Cyan
}

Write-Host ""
Write-Host "AFCON360 USER APP - DEVELOPMENT SESSION" -ForegroundColor Cyan
Write-Host ("Connection mode : " + $ConnectionMode)
Write-Host ("API base        : " + $ApiBaseUrl)
Write-Host ("Metro address   : http://" + $MetroHost + ":" + $MetroPort)
Write-Host ("Backend folder  : " + $BackendRoot)
Write-Host "Native rebuild  : not performed by this script"
Write-Host ""

if (-not $SkipApiStart) {
    Start-LocalApi -Root $BackendRoot -BindAddress $BindAddress -ExpectedLanAddress $MetroHost -Port $ApiPort
} else {
    $existingApiListeners = @(Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue)
    if ($existingApiListeners.Count -eq 0) {
        throw "-SkipApiStart was selected, but no server is listening on port 5000."
    }

    $expectedAddresses = @("127.0.0.1", "::1")
    if ($ConnectionMode -eq "Lan") {
        $expectedAddresses = @("0.0.0.0", "::", $MetroHost)
    }
    $matchingApi = @($existingApiListeners | Where-Object {
        $expectedAddresses -contains $_.LocalAddress
    })
    if ($matchingApi.Count -eq 0) {
        throw "The existing API is not listening on the interface required by this connection mode."
    }

    Write-Warning "Reusing an API started outside this helper. Confirm FLASK_DEBUG=false; this script cannot inspect another process environment."
    if (-not (Test-ApiReady -Url "http://127.0.0.1:5000")) {
        throw "The existing API did not pass /api/health/ready."
    }
}

$metroListeners = @(Get-NetTCPConnection -LocalPort $MetroPort -State Listen -ErrorAction SilentlyContinue)
if ($metroListeners.Count -gt 0) {
    $pids = @($metroListeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    throw ("Metro port {0} is already in use by PID(s) {1}. Stop the old Metro process and rerun so the current network/API configuration is applied." -f $MetroPort, $pids)
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
    if ($listener) {
        $metroReady = $true
        break
    }
    Start-Sleep -Seconds 2
}
if (-not $metroReady) {
    throw ("Metro did not start listening on port {0}. Check the separate Metro PowerShell window." -f $MetroPort)
}

if ($adb -and $DeviceSerial) {
    & $LaunchScript -ConnectionMode $ConnectionMode -MetroHost $MetroHost -Port $MetroPort -ApiPort $ApiPort -DeviceSerial $DeviceSerial
    if ($LASTEXITCODE -ne 0) {
        throw "Development-client launch helper failed."
    }
} else {
    Write-Host "No ADB device selected. Scan the QR code shown by Metro on the phone." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "AFCON360 USER APP DEVELOPMENT SESSION READY" -ForegroundColor Green
Write-Host ("API: " + $ApiBaseUrl)
Write-Host ("Metro: http://" + $MetroHost + ":" + $MetroPort)
Write-Host "Use Connection settings to apply the API address supplied by this Metro session."
Write-Host ("For LAN mode, Windows Firewall must allow private-network TCP ports 5000 and " + $MetroPort + ".")
Write-Host "No native build, APK reinstall, EAS build or OTA publication is performed."
