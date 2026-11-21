<# 
.SYNOPSIS
    Start Metro bundler on hotspot network (handles both phone-hotspot and laptop-hotspot)
.DESCRIPTION
    Auto-detects laptop IP on hotspot network and starts Expo Metro on 0.0.0.0:8081.
    Supports both scenarios:
    1. Phone hotspot ON, laptop joins -> laptop gets 192.168.43.x
    2. Laptop hotspot ON, phone joins -> laptop is 192.168.43.1 (or 192.168.137.1)
#>

param()

# Detect hotspot mode
$phoneHotspotIP = (Get-NetIPAddress -AddressFamily IPv4 | 
    Where-Object { $_.IPAddress -like "192.168.43.*" -and $_.PrefixOrigin -ne "WellKnown" }).IPAddress

$laptopHotspotIP = (Get-NetIPAddress -AddressFamily IPv4 | 
    Where-Object { $_.IPAddress -in @("192.168.43.1", "192.168.137.1") }).IPAddress

$mode = ""
$laptopIP = ""

if ($phoneHotspotIP) {
    $mode = "PHONE HOTSPOT"
    $laptopIP = $phoneHotspotIP
}
elseif ($laptopHotspotIP) {
    $mode = "LAPTOP HOTSPOT"
    $laptopIP = $laptopHotspotIP
}
else {
    Write-Error "No hotspot network detected"
    Write-Host "Expected one of:" -ForegroundColor Yellow
    Write-Host "  Phone hotspot ON  -> laptop IP 192.168.43.x" -ForegroundColor Yellow
    Write-Host "  Laptop hotspot ON -> laptop IP 192.168.43.1 or 192.168.137.1" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Current IPs:" -ForegroundColor Yellow
    Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress, InterfaceAlias, PrefixOrigin | Format-Table -AutoSize
    exit 1
}

Write-Host "===========================================" -ForegroundColor Green
Write-Host "  METRO WIFI MODE - $mode" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green
Write-Host "Laptop IP: $laptopIP" -ForegroundColor Cyan
Write-Host "Metro binds to: 0.0.0.0:8081" -ForegroundColor Cyan

if ($mode -eq "PHONE HOTSPOT") {
    Write-Host "Phone Metro URL:    http://$laptopIP:8081" -ForegroundColor Cyan
    Write-Host "Phone API URL:      http://$laptopIP:5000" -ForegroundColor Cyan
}
else {
    Write-Host "Phone Metro URL:    http://$laptopIP:8081" -ForegroundColor Cyan
    Write-Host "Phone API URL:      http://$laptopIP:5000" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Note: On laptop hotspot, phone connects to $laptopIP" -ForegroundColor Yellow
}

Write-Host "===========================================" -ForegroundColor Green
Write-Host ""
Write-Host "On phone, set in app Settings:" -ForegroundColor Yellow
Write-Host "  Connection > API Base: http://$laptopIP:5000" -ForegroundColor Yellow
Write-Host "  Metro > URL:         http://$laptopIP:8081" -ForegroundColor Yellow
Write-Host ""
Write-Host "Then run in another terminal:" -ForegroundColor Yellow
Write-Host "  .\launch-phone.ps1 $laptopIP" -ForegroundColor Yellow
Write-Host ""

$env:AFCON360_PREVIEW_BUILD = "true"
$env:AFCON360_RELEASE_BUILD = "false"

npx expo start --dev-client --host lan --port 8081