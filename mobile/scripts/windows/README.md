# Windows User App development helpers

These helpers are for the **User App** only. They target the configured development client:

- Android package: `space.pamoja.afcon360.user.preview.dev`
- Deep-link scheme: `afcon360-preview-dev`
- EAS update channel: `user-development-client`

## Start Metro

Run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-metro.ps1
```

Keep that PowerShell window open. The script resolves the workspace relative to its own location, sets the correct dev-client environment, and starts Metro only. It does not compile or reinstall the APK, start Flask, modify Windows Firewall rules, or stop existing processes.

Optional:

```powershell
# Use a local API server instead of the public Pamoja API.
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-metro.ps1 -ApiBaseUrl "http://192.168.43.100:5000"

# Clear Metro's cache when investigating a bundler/cache problem.
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-metro.ps1 -ClearCache
```

The phone and laptop must be able to reach one another on the same Wi-Fi/hotspot network. Expo prints a development-client QR code and URL for manual launch.

## Launch the installed development client over ADB

In a second PowerShell window, after Metro is listening:

```powershell
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\launch-user-dev-client.ps1
```

The script discovers ADB from PATH, `ANDROID_HOME`, `ANDROID_SDK_ROOT`, or the standard per-user Android SDK directory. It requires one authorized device unless `-DeviceSerial` is supplied. It verifies that the expected development-client package is installed before opening its Metro deep link.

If automatic LAN address selection is not correct, provide the laptop address:

```powershell
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\launch-user-dev-client.ps1 -MetroHost "192.168.43.100"
```

## Rebuild boundary

- TypeScript/JavaScript and compatible assets: Metro Fast Refresh; no APK rebuild.
- Native dependencies, native app configuration, Android permissions, or native plugins: a new development-client APK is required.
- These helpers do not change EAS credentials, publish OTA updates, modify production configuration, or write to the production server.
