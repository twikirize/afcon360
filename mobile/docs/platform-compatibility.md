# AFCON360 mobile platform compatibility policy

## One source system, four store products

AFCON360 has one React Native/Expo workspace in this repository. It contains two app entry points:

- `apps/user`: customer, rider and fan experience.
- `apps/driver`: approved driver and transport-operator experience.

Common components and behavior are shared through `packages/`. Authentication, device sessions, API contracts and other shared domain behavior must not drift into separate Android and iOS implementations.

The source system is shared; the store binaries are not interchangeable:

| Product | Android deliverable | Apple deliverable |
|---|---|---|
| AFCON360 User | Play-signed production AAB | App Store-signed IPA/archive |
| AFCON360 Driver | Play-signed production AAB | App Store-signed IPA/archive |

Internal preview APKs are only for direct Android testing. They are not Play Store packages. Apple must receive its own iOS archive/IPA. User and Driver app identities remain separate.

## Current SDK 58 operating-system baseline

| Setting | Baseline |
|---|---:|
| Minimum Android OS | Android 7.0 / API 24 |
| Android compile SDK | 37 |
| Android target SDK | 36 |
| Minimum iOS deployment target | iOS 16.4 |
| Minimum Xcode for SDK 58 | 26.4 |

Both app configs explicitly declare iOS deployment target 16.4. The generated Android projects must retain minSdk 24, compileSdk 37 and targetSdk 36; CI validates these settings in each built APK and installs the APK at the oldest supported API.

The SDK compile/target versions are build and store-submission settings. They do not mean a device must run Android 16 or iOS 26: both apps retain older operating-system support down to their declared deployment minimums.

## Continuous-integration compatibility matrix

Each User and Driver preview APK must:

1. Build from the shared workspace.
2. Pass signature verification, package identity, minSdk 24, target SDK 36+, backup-policy and payload checks.
3. Pass manifest checks for blocked legacy storage/overlay permissions and for cleartext/debuggable settings.
4. Install and launch on Android API 24, 29, 33 and 36 emulators.

Each User and Driver iOS app must:

1. Pass Expo dependency compatibility checks.
2. Generate its native iOS project and CocoaPods workspace.
3. Build with Xcode 26.4 or later.
4. Assert iOS deployment target 16.4 and the expected bundle ID.
5. Install and launch on an iOS 26.4 simulator.

These jobs produce CI evidence only. The PR-capable workflow uses temporary Android signing and does not publish a GitHub Release. CI simulator/emulator success is not physical-device acceptance or store approval.

## Limits of automated evidence

Before public release, test at least:

- Older Android hardware at/near API 24, a mid-range Android device, and a current Android device.
- Older supported iPhones/iPads on iOS 16.4 or later and a current iOS device.
- Fresh install, upgrade, sign-in/MFA, permission denied/granted, network loss/recovery, low storage and account deletion.
- Driver foreground location behavior and permission changes on real devices.

Record actual device models and OS build numbers with release evidence. Never claim all Android or Apple devices are supported solely from one emulator/simulator run.

## Store package and credential policy

- Android preview: disposable CI signing key, APK output, run-scoped Actions artifact.
- Android production: production signing and Google Play App Signing, AAB output.
- iOS simulator validation: unsigned simulator app, not an IPA.
- iOS production: Apple distribution signing, archive/IPA and App Store Connect.
- Never commit signing keys, passwords, Apple API keys, provisioning profiles or GitHub secrets.
- Keep User and Driver identifiers and signing identities distinct.
