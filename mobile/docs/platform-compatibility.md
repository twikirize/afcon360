# AFCON360 mobile platform compatibility policy

## One source system, four store products

AFCON360 has one React Native/Expo workspace in this repository. It contains two app entry points:

- `apps/user`: customer, rider and fan experience.
- `apps/driver`: approved driver and transport-operator experience.

Common components and behavior are shared through `packages/`. Authentication, device sessions, wallet display, API contracts and other shared domain behavior must not drift into separate Android and iOS implementations.

The source system is shared; the store binaries are not interchangeable:

| Product | Android deliverable | Apple deliverable |
|---|---|---|
| AFCON360 User | Play-signed production AAB | App Store-signed IPA/archive |
| AFCON360 Driver | Play-signed production AAB | App Store-signed IPA/archive |

Internal preview APKs are only for direct Android testing. They are not Play Store packages. Apple must receive its own iOS archive/IPA. Both app identities and signing credentials remain separate.

## Current SDK 58 operating-system baseline

The Expo SDK 58 reference currently states:

| Setting | Current value |
|---|---:|
| Minimum Android OS | Android 7.0 / API 24 |
| Android compile SDK | 37 |
| Android target SDK | 36 |
| Minimum iOS deployment target | iOS 16.4 |
| Minimum Xcode | 26.4 |

Both app configs explicitly declare iOS deployment target 16.4. Android's generated Expo SDK 58 project must retain minSdk 24, compileSdk 37 and targetSdk 36; the build workflow validates these values from the produced APK and installs the same signed APK at the minimum API.

Google Play requires new apps and updates to target API 36 or higher from 31 August 2026. Apple requires App Store Connect uploads to use Xcode 26 or later with an iOS 26 SDK from 28 April 2026. These store submission SDK requirements do not mean users must run Android 16 or iOS 26: the app can still support older OS versions down to its declared deployment minimum.

## Continuous integration compatibility matrix

Each User and Driver preview APK must:
1. Build from the shared workspace.
2. Pass signature verification, package ID, minimum SDK 24, target SDK 36+, and native payload checks.
3. Install and launch on Android API 24, 29, 33 and 36 emulators.

Each User and Driver iOS app must:
1. Pass Expo dependency compatibility checks.
2. Generate its native iOS project and CocoaPods workspace.
3. Build with an Xcode 26.4+ toolchain.
4. Assert iOS deployment target 16.4 and the expected bundle ID.
5. Install and launch on an iOS 26.4 simulator.

The Android and iOS jobs are release gates. The preview download release is not published unless all platform compatibility jobs pass.

## Limits of automated evidence

Emulator/simulator tests are a baseline, not a substitute for physical-device testing. Before public release, test at least:
- Older Android hardware at/near API 24, a mid-range Android device, and a current Android 16 device.
- Older supported iPhones/iPads on iOS 16.4 or later and a current iOS device.
- Fresh install, update over an earlier build signed with the same key, sign-in/MFA, permission denied/granted, network loss/recovery, low storage and account deletion.
- Driver foreground location behavior and battery/permission handling on real devices.

The actual tested-device list and OS build numbers must be recorded with release evidence. Never claim all Android or Apple devices are supported solely from one emulator/simulator run.

## Store package and credential policy

- Android preview: dedicated internal preview keystore, APK output.
- Android production: production signing and Google Play App Signing, AAB output.
- iOS preview and production: Apple development/distribution signing as appropriate; App Store submission requires the authorized Apple Developer team, registered bundle IDs, distribution certificate/profile, and App Store Connect access.
- Never reuse or commit signing keys, passwords, Apple API keys, provisioning profiles or GitHub secrets.
- Keep User and Driver identifiers and signing identities distinct.

## Official platform references

- [Expo SDK 58 platform support](https://docs.expo.dev/versions/v58.0.0/)
- [Google Play target API requirements](https://support.google.com/googleplay/android-developer/answer/11926878)
- [Apple App Store submission requirements](https://developer.apple.com/news/upcoming-requirements/)
- [Expo Build Properties](https://docs.expo.dev/versions/v58.0.0/sdk/build-properties/)
