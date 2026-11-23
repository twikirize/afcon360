$adb = "C:\Users\OBED\AppData\Local\Android\Sdk\platform-tools\adb.exe"
$selectedDevice = "HQ61BR0F03"
$PackageId = "space.pamoja.afcon360.user.preview.dev"
$Scheme = "afcon360-preview-dev"
$Port = 8081
$ApiPort = 5000
$ListenerPort = 8082
$MetroHost = "127.0.0.1"

Write-Host "Setting up USB ADB reverse tunnels..." -ForegroundColor Cyan
& $adb -s $selectedDevice reverse "tcp:8081" "tcp:8081"
if ($LASTEXITCODE -ne 0) { throw "ADB could not forward the Metro port over USB." }

& $adb -s $selectedDevice reverse "tcp:5000" "tcp:5000"
if ($LASTEXITCODE -ne 0) { throw "ADB could not forward the laptop API port over USB." }

& $adb -s $selectedDevice reverse "tcp:8082" "tcp:8082"
if ($LASTEXITCODE -ne 0) { throw "ADB could not forward the Metro listener port over USB." }

$metroUrl = "http://127.0.0.1:8081"
$encodedUrl = [Uri]::EscapeDataString($metroUrl)
$deepLink = $Scheme + "://expo-development-client/?url=" + $encodedUrl

Write-Host ""
Write-Host "Launching AFCON360 User development client" -ForegroundColor Cyan
Write-Host "Connection : Usb"
Write-Host "Device     : $selectedDevice"
Write-Host "Package    : $PackageId"
Write-Host "Metro URL  : $metroUrl"
Write-Host "API URL    : http://127.0.0.1:$ApiPort (ADB reverse)"
Write-Host ""

& "C:\Users\OBED\AppData\Local\Android\Sdk\platform-tools\adb.exe" -s $selectedDevice shell am start -a android.intent.action.VIEW -d ($Scheme + "://expo-development-client/?url=" + [Uri]::EscapeDataString("http://127.0.0.1:8081")) -p $PackageId
if ($LASTEXITCODE -ne 0) { throw "Android failed to open the development-client deep link." }

Write-Host ""
Write-Host "AFCON360 User development client launched" -ForegroundColor Green
Write-Host "The app should now connect to Metro via USB reverse tunnel."