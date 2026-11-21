[CmdletBinding()]
param(
    [string]$MetroHost,
    [ValidateRange(1024, 65535)]
    [int]$Port = 8081,
    [string]$DeviceSerial
)

$ErrorActionPreference = "Stop"
$PackageId = "space.pamoja.afcon360.user.preview.dev"
$Scheme = "afcon360-preview-dev"

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
            if ($config.IPv4DefaultGateway) { $score += 100 }
            if ($address -like "192.168.43.*" -or $address -like "192.168.137.*") { $score += 50 }
            elseif ($address -like "192.168.*" -or $address -like "10.*") { $score += 30 }
            elseif ($address -match "^172\.(1[6-9]|2[0-9]|3[01])\.") { $score += 20 }
            if ($config.InterfaceAlias -match "(?i)wi-?fi|wireless|ethernet") { $score += 10 }

            $candidates += [PSCustomObject]@{ Address = $address; Score = $score }
        }
    }
    if ($candidates.Count -eq 0) { return $null }
    return ($candidates | Sort-Object Score -Descending | Select-Object -First 1).Address
}

if (-not $MetroHost) { $MetroHost = Find-LanAddress }
if (-not $MetroHost) { throw "Could not detect the laptop's LAN IPv4 address. Supply it with -MetroHost." }

$parsedIp = $null
if (-not [System.Net.IPAddress]::TryParse($MetroHost, [ref]$parsedIp) -or
    $parsedIp.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw "MetroHost must be an IPv4 address reachable by the phone."
}

$metroListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $metroListener) { throw "Metro is not listening on port $Port. Start start-user-metro.ps1 first and leave it running." }

$adb = Find-Adb
if (-not $adb) { throw "ADB was not found. Install Android SDK platform-tools or set ANDROID_HOME / ANDROID_SDK_ROOT." }

$deviceOutput = @(& $adb devices)
if ($LASTEXITCODE -ne 0) { throw "ADB could not list connected Android devices." }
$onlineDevices = @()
foreach ($line in $deviceOutput) {
    if ($line -match "^(\S+)\s+device$") { $onlineDevices += $Matches[1] }
}

if ($DeviceSerial) {
    if ($onlineDevices -notcontains $DeviceSerial) {
        throw "Device '$DeviceSerial' is not connected and authorized. Online devices: $($onlineDevices -join ', ')"
    }
    $selectedDevice = $DeviceSerial
}
elseif ($onlineDevices.Count -eq 1) {
    $selectedDevice = $onlineDevices[0]
}
elseif ($onlineDevices.Count -gt 1) {
    throw "More than one Android device is connected. Specify -DeviceSerial. Devices: $($onlineDevices -join ', ')"
}
else {
    throw "No authorized ADB device is connected. Connect by USB and approve debugging, or open the dev client using the Metro QR code."
}

$installed = @(& $adb -s $selectedDevice shell pm path $PackageId)
if ($LASTEXITCODE -ne 0 -or -not ($installed -match "package:")) {
    throw "The development client '$PackageId' is not installed on '$selectedDevice'. Install the User development-client APK first."
}

$metroUrl = "http://" + $MetroHost + ":" + $Port
$encodedUrl = [Uri]::EscapeDataString($metroUrl)
$deepLink = $Scheme + "://expo-development-client/?url=" + $encodedUrl

Write-Host ""
Write-Host "Launching AFCON360 User development client" -ForegroundColor Cyan
Write-Host "Device    : $selectedDevice"
Write-Host "Package   : $PackageId"
Write-Host "Metro URL : $metroUrl"
Write-Host ""
& $adb -s $selectedDevice shell am start -a android.intent.action.VIEW -d $deepLink -p $PackageId
if ($LASTEXITCODE -ne 0) { throw "Android failed to open the development-client deep link." }
