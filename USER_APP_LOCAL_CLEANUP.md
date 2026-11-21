# User App Local Snapshot Cleanup and Dynamic Development Connection

**Repository:** twikirize/afcon360  
**Branch:** reconcile/user-local-files-20261121  
**Recovery snapshot:** d82dfc2b2fbe00ba7b1bb654db910f66cda62e42

## Reconciliation changes

The original 39-file local snapshot remains available in Git history. The active branch excludes the mismatched generated Android project, duplicate Home/Ride prototype screens, machine-specific launcher wrappers, and one-time diagnostics. The live offline-first Home and request-first Ride routes remain intact.

The captured Android project did not match the current dynamic .preview.dev package, scheme or Expo Updates configuration. This branch keeps the User App on Expo Continuous Native Generation (CNG), with native directories excluded from source and EAS archives.

## Dynamic development connection

The Windows helper scripts support phone-hotspot-to-laptop, laptop-hotspot-to-phone, ordinary trusted Wi-Fi/LAN, USB ADB reverse for both Metro and the local Flask API, and manual adapter/IP selection.

The one-command helper discovers the repo and backend locations, chooses USB only when an authorized ADB device has the .preview.dev app installed (otherwise LAN), starts the local Flask API with debug disabled and the appropriate bind, waits for database readiness, starts Metro with the development-client package/scheme/channel, and opens the installed dev client where ADB is available. When the APK is not installed, Auto falls back to LAN/QR rather than failing after starting services.

The in-app Connection settings no longer call the missing /api/health/server-urls endpoint. They use the API URL supplied by the current Metro manifest or a manual server entry, and verify /api/health/ready before switching. HTTP loopback is permitted only for preview USB ADB reverse on port 5000; public/remote servers still require HTTPS.

The helper refuses to stop or silently reuse an unknown API process. Existing API reuse requires explicit -SkipApiStart and a user-verified safe debug/bind configuration. Wi-Fi/hotspot access is intended for trusted local networks and Windows Private firewall profiles.

## Update and build discipline

- Metro Fast Refresh is the immediate path for ordinary JavaScript/TypeScript and compatible asset changes.
- The release-like preview APK uses its configured EAS Update channel for launch-time OTA when platform and native runtime match.
- The development client can preview published compatible Expo Updates through its Extensions tab.
- Native dependency/configuration changes need a new native APK.
- The disposable authenticated-journey APK is rebuilt for each exact source commit (no old cache-prefix fallback), and the emulator tests that commit's embedded JavaScript. It runs only after dependency/config, strict TypeScript, Android/iOS bundle export and navigation checks pass.
- The distributable development-client APK remains reusable across JavaScript-only changes; its cache is keyed by native fingerprint, EAS development profile, app version and build recipe. It is built or reused only after the disposable authenticated journey succeeds.
- Compatible bundles are separately published to the development-client preview branch and the release-like user-development OTA branch. The dev-client APK uses Metro for immediate development; the release-like preview APK uses ON_LOAD OTA when runtime/platform/channel match.

## Scope and safety

- All changes are confined to the reconciliation branch.
- The User App base and offline-first working branch were not modified.
- The original local snapshot is retained as a recovery commit.
- No production server, production database, EAS credential, or production release channel was changed.
- No APK was built or installed by the reconciliation process itself.
- PowerShell scripts are statically validated by GitHub CI and still require actual Windows network/ADB verification before transfer to the offline-first working branch.
