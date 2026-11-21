<# 
.SYNOPSIS
    Launch AFCON360 dev client on phone with WiFi Metro URL
.DESCRIPTION
    Starts the app with deep link pointing to Metro on laptop IP.
    Run after start-wifi.ps1 is running.
#>

param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$LaptopIP
)

if (-not $LaptopIP) {
    Write-Error "Usage: .\launch-phone.ps1 <LaptopIP>"
    Write-Host "Example: .\launch-phone.ps1 192.168.43.142"
    exit 1
}

# Validate IP format
if ($LaptopIP -notmatch '^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$') {
    Write-Error "Invalid IP format: $LaptopIP"
    exit 1
}

$metroUrl = "http://$LaptopIP:8081"
$encodedUrl = [System.Web.HttpUtility]::UrlEncode($metroUrl)
$deepLink = "afcon360-preview://expo-development-client/?url=$encodedUrl"

$adb = "C:\Users\OBED\AppData\Local\Android\Sdk\platform-tools\adb.exe"

if (-not (Test-Path $adb)) {
    Write-Error "ADB not found at: $adb"
    exit 1
}

Write-Host "===========================================" -ForegroundColor Green
Write-Host "  LAUNCHING ON PHONE (WiFi)" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green
Write-Host "Laptop IP:     $LaptopIP" -ForegroundColor Cyan
Write-Host "Metro URL:     $metroUrl" -ForegroundColor Cyan
Write-Host "Deep Link:     $deepLink" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Green

Write-Host "Stopping any running instance..." -ForegroundColor Yellow
& $adb shell am force-stop space.pamoja.afcon360.user.preview
Start-Sleep -Seconds 2

Write-Host "Clearing logcat..." -ForegroundColor Yellow
& $adb logcat -c

Write-Host "Starting app..." -ForegroundColor Yellow
& $adb shell am start -a android.intent.action.VIEW -d $deepLink

Write-Host ""
Write-Host "Done. Check phone - should load Home screen." -ForegroundColor Green
Write-Host "If error screen appears, verify:" -ForegroundColor Yellow
Write-Host "  1. start-wifi.ps1 is running in other terminal" -ForegroundColor Yellow
Write-Host "  2. Phone is connected to same hotspot" -ForegroundColor Yellow
Write-Host "  3. App Settings > API = http://$LaptopIP:5000" -ForegroundColor Yellow
Write-Host "  4. App Settings > Metro = http://$LaptopIP:8081" -ForegroundColor Yellow