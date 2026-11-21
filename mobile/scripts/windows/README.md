# Windows User App development helpers

These helpers are for the User App only. They target the isolated development client:

- Android package: space.pamoja.afcon360.user.preview.dev
- Deep-link scheme: afcon360-preview-dev
- Expo Update channel: user-development-client

## One-command development startup

From any PowerShell working directory, run:

    powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1

The script detects the connection path:

- USB: when an authorized ADB device is attached, it sets ADB reverse tunnels for Metro (8081) and the local API (5000). The phone uses 127.0.0.1 and the laptop backend remains bound to loopback.
- Wi-Fi / phone hotspot / laptop hotspot: it selects the laptop's active private IPv4 address, starts the API bound to 0.0.0.0 with Flask debug mode disabled, and starts Metro using LAN discovery. It recognises common Android phone-hotspot and Windows mobile-hotspot ranges.
- Manual override: use -ConnectionMode Lan or -ConnectionMode Usb when you want a specific transport. Use -MetroHost to specify the laptop adapter address when multiple active networks make automatic choice ambiguous.
- The app's Connection settings include "Use server for this development session". It applies the API address injected by the current Metro session and verifies /api/health/ready before changing servers.

By default the backend is expected in the sibling folder afcon360_app. To use a different checkout:

    powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1 -BackendRoot "D:\work\afcon360_app"

If the phone is connected over more than one ADB device, specify -DeviceSerial. To force Wi-Fi even while USB debugging is connected, use -ConnectionMode Lan.

## What the startup script does not do

- It does not run Gradle, Expo Prebuild, or compile/install an APK.
- It does not edit Windows Firewall rules. For LAN mode, Windows Firewall must permit inbound TCP ports 5000 (local API) and 8081 (Metro) on the trusted Private network profile.
- It does not enable the Flask/Werkzeug debugger. The laptop API is launched with FLASK_DEBUG=false.
- It does not publish OTA updates or contact the production database/server intentionally; the backend uses the local checkout and its APP_ENV=local configuration.
- It does not overwrite the app's saved API server silently. After Metro starts with a new address, use the in-app connection button once; switching servers clears saved credentials/offline cache so accounts cannot be mixed between environments.

## Individual helpers

start-user-metro.ps1 starts Metro only and accepts -ConnectionMode Lan|Usb, -ApiBaseUrl, -Port, and -ClearCache.

launch-user-dev-client.ps1 opens the already installed development-client APK over ADB. In USB mode it sets reverse tunnels for ports 8081 and 5000. In LAN mode it opens the laptop's current private IPv4 URL.

## Fast Refresh, OTA, and APK rebuild boundary

- TypeScript/JavaScript and compatible assets: Metro Fast Refresh while the dev client is connected; no APK rebuild.
- Compatible release/preview JavaScript updates: Expo Update (OTA) only for builds with matching runtime version, platform and channel. Metro Fast Refresh and OTA are different delivery paths.
- Native dependencies, native app config, Android permissions, or native plugins: new development-client APK required, then install/update that binary.
- The helper scripts do not change EAS credentials, sign binaries, publish updates, or write to a production server.

Before any new APK build, CI must first pass dependency/config checks, strict TypeScript checking, Android/iOS bundle export, route/accessibility contracts, and the authenticated Android screen-loading journey. A native APK is built only when the native fingerprint changes or the first required development-client binary does not yet exist.
