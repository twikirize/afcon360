# AFCON360 User App — Windows development workflow

These scripts are for the User App only. They target the isolated Metro development client:

- Android package: space.pamoja.afcon360.user.preview.dev
- App deep-link scheme: afcon360-preview-dev
- Metro port: 8081
- Laptop Flask API port: 5000
- EAS profile: development (internal APK)

## Start a complete local development session

From the repository root, run one command:

    powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1

The script discovers the repo and backend folders relative to itself. By default, the backend is expected in the sibling folder afcon360_app. Set AFCON360_BACKEND_ROOT or pass -BackendRoot if the backend checkout is elsewhere.

Running this one-command helper starts the local Flask API and Metro together. Running Flask directly (for example, `python app.py`) does not start Metro by itself.

## Choose Local development or live Pamoja

The default `-TargetEnvironment Auto` preserves the established local workflow: it starts the laptop Flask API and Metro. To check the live public Pamoja target without starting either local process, run:

    powershell -ExecutionPolicy Bypass -File .\\mobile\\scripts\\windows\\start-user-dev.ps1 -TargetEnvironment Pamoja

Auto mode also detects Pamoja from an explicit API target:

    $env:AFCON360_API_BASE_URL = "https://www.pamoja.space"
    & .\\mobile\\scripts\\windows\\start-user-dev.ps1

The Pamoja path accepts only the public HTTPS Pamoja host and performs a read-only `/api/health/ready` check. It does not start local Flask, Metro, ADB tunnels, or publish an app update. Remove the process-level variable with `Remove-Item Env:AFCON360_API_BASE_URL` to return to the default local workflow, or pass `-TargetEnvironment Local`.

**Metro is for internal developers only.** It serves unfinished JavaScript/TypeScript app code from a developer's laptop. It does not watch or download changes from the Pamoja server. Normal preview/live app users do not need Metro.

## Connection modes

Auto is the default.

- USB: if an authorized Android device is available through ADB and the .preview.dev development-client APK is installed, the helper uses adb reverse for both Metro (8081) and Flask (5000). The phone connects through 127.0.0.1 while the laptop API remains bound to loopback. Auto checks for the package before selecting USB; if it is not installed, Auto falls back to LAN and shows the Metro QR flow rather than failing after startup. Explicit -ConnectionMode Usb fails early when the app is missing.
- Phone hotspot → laptop: Flask starts on all interfaces with its debugger disabled and prints the reachable laptop IP addresses. The helper shows those same addresses and asks you to choose the one on the phone-hotspot network.
- Laptop hotspot → phone: Flask prints the laptop's current hotspot address (for example, 192.168.137.1). The helper asks you to select that address; it does not guess or rank a network adapter.
- Ordinary shared Wi-Fi/Ethernet: Flask prints the addresses it detects for the active laptop interfaces. Choose the address on the same network as the phone.
- Manual selection: pass -MetroHost with the laptop IPv4 address when you already know which Flask address to use. The in-app Connection screen also permits manual API and Metro URLs.

Force a mode:

    powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1 -ConnectionMode Lan

    powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1 -ConnectionMode Usb

    powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1 -ConnectionMode Lan -MetroHost "192.168.43.100"

The helper starts the local API with APP_ENV=local, FLASK_DEBUG=false, and FLASK_HOST=0.0.0.0 for Wi-Fi/hotspot (or loopback for USB). It waits for /api/health/ready (database readiness). For Wi-Fi/hotspot it then presents the addresses reported by Flask's existing "Server listening" startup output and asks you to choose the one that matches the phone's current connection. The selected address is used for both the app API and Metro. Metro runs in a separate PowerShell window. If ADB and the development APK are available, the helper opens the installed development client; otherwise scan the QR code printed by Metro.

The helper does not kill an unknown process that already owns port 5000 or 8081. An API process previously started by this helper may be reused; an unrelated listener is rejected. Use -SkipApiStart only when you deliberately started the local API yourself and have confirmed its debug mode and bind address. The helper never enables the Flask/Werkzeug debugger on the LAN. If Flask is reused after the laptop changes networks, the helper also offers current active adapter addresses so you can make the same explicit selection for the new connection.

## Use the laptop API from the app

After Metro opens the User App, open Connection settings:

- Use server for this development session applies the API address supplied by the current Metro session and verifies the database-readiness endpoint before switching.
- Enter another preview server lets you enter an API address manually.
- Metro Bundler (Fast Refresh) lets you save and open a Metro URL manually if needed.
- Public Pamoja returns the app to the public HTTPS API. The Connection screen identifies this as the live Pamoja server. In a development-client build, Metro remains an optional developer-only code loader; non-development builds do not show its controls.

For Wi-Fi/hotspot, the laptop API is http://<laptop-private-ip>:5000. For USB, it is http://127.0.0.1:5000 after ADB reverse is enabled. The app clears stored sign-in credentials and the offline account cache when changing API environments, preventing local test accounts and cached account information from being mixed with public Pamoja.

Plain HTTP is only for private internal testing or the USB loopback tunnel. It is not encrypted over Wi-Fi/hotspot. Use a trusted network and test accounts only; never send production credentials or financial information over local HTTP.

For LAN mode, Windows Firewall must permit inbound TCP ports 5000 and 8081 on a trusted Private network profile. These scripts do not open public firewall access or weaken Windows Firewall rules. If Windows classifies a trusted hotspot as Public, use USB or change that trusted network's profile to Private in Windows before allowing local development traffic.

## Immediate edits, OTA updates, and APK rebuilds

There are two separate update paths:

1. Metro Fast Refresh — internal day-to-day development only. While the development client is connected to Metro, JavaScript/TypeScript and compatible assets can refresh immediately. No APK rebuild is needed for ordinary screen, navigation, styling, and business-logic changes. Metro serves code from the developer laptop, not from Pamoja.
2. Expo Updates — distributing compatible app-code changes to installed preview/live builds. The app checks its configured update channel on launch. The release-like preview build uses its configured user-development channel; the production build uses the production channel. An OTA must be intentionally published to the matching channel and match the app's platform and native runtime. A new native fingerprint is not OTA-compatible.
3. Backend/API changes — once deployed on Pamoja, the live app receives the server-side behaviour through its normal HTTPS API requests. No Metro session or app reinstall is required for backend-only changes.

The current CI flow publishes compatible updates to the isolated `user-development-client` channel and the release-like `user-development` preview channel. It does not automatically publish to the `production` channel. Production OTA publication remains a deliberate release action and must be enabled only after the production release gate and approval are in place.

The Metro development-client APK is a debug development build. Use Metro for the immediate edit-and-review loop. Use the release-like preview build for automatic launch-time OTA validation, or the development client's Extensions tab to inspect a published update. Do not assume a debug development client automatically applies the same OTA behaviour as a standalone release build.

A new APK is required when native dependencies, Expo SDK/native configuration, app permissions, native plugins, or another native build input changes. The distributable development-client APK is gated behind static checks, Android/iOS JavaScript bundle exports, and the authenticated Android screen journey. CI first uses a disposable Android test build to prove the app opens and its main screens load; only then is the distributable Metro development-client APK built or reused.

## Individual helpers

- start-user-metro.ps1 starts Metro only. It accepts -ConnectionMode Lan|Usb, -ApiBaseUrl, -Port, and -ClearCache.
- launch-user-dev-client.ps1 opens the installed .preview.dev app over ADB. USB mode creates both reverse tunnels; LAN mode opens the current laptop IPv4 URL.
- start-user-dev.ps1 is the one-command orchestrator for API, Metro and device launch.

No helper runs Gradle, Expo Prebuild, EAS Build, EAS Update, production database writes, or production server operations.
