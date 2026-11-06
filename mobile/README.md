# AFCON360 Native Mobile

Two separate native products share one React Native foundation:

- **AFCON360 User** — customers, riders and fans.
- **AFCON360 Driver** — approved drivers and transport operators.

Both use Expo SDK 58, React Native 0.88.1, React 19.3 and TypeScript 6. Flask remains the system of record. Mobile clients use HTTPS APIs and never connect directly to PostgreSQL.

## Implemented in this branch

- Separate Android application IDs and iOS bundle IDs.
- Shared native UI, HTTPS API client and operating-system SecureStore.
- Native password login, in-app email-code password recovery, TOTP/backup-code MFA, 10-minute access tokens, 30-day rotating refresh credentials and device logout/revocation. SMS MFA is intentionally unsupported until the existing Auth verifier supports it.
- User ride flow: GEO search, signed fare quotes, Wallet-certified payment methods, request-first Transport creation, activity and tracking.
- Driver flow: go-live checklist, offer polling/accept/decline, trip progress, foreground driver-initiated GPS, cash receipt confirmation and currency-separated captured earnings.
- In-app account closure and in-app password recovery. Password recovery currently requires an active account with a registered email address; accounts using the legacy no-email security-question recovery still need the existing website recovery process or support.
- Website app/share page at `/apps`, EAS build profiles and a PR-safe compatibility workflow.

## Platform compatibility and current release gates

The native branch is not merged or deployed. The compatibility workflow is configured to build and verify both Android preview APKs, install and launch both apps on Android API 24, 29, 33 and 36 emulators, and build/install/launch both iOS apps on an iOS 26.4 simulator. It also verifies the iOS 16.4 deployment minimum, expected bundle IDs, Android package IDs, Android minimum SDK 24 and target SDK 36 or higher.

These are CI emulator/simulator checks, not proof of physical-device acceptance or store readiness. The latest workflow run on this branch must pass before these checks are treated as verified. Real Android and iPhone/iPad testing remains required.

Android CI artifacts use a newly generated, short-lived signing key for each run. They are for test validation only, are not published to the `mobile-preview` GitHub Release, and are not Google Play packages. A new run's APK will not update an earlier test installation signed by a different temporary key; preserve any required local test data before uninstalling an older test build.

iOS CI builds are simulator builds only. They do not create a signed App Store/TestFlight IPA or upload anything to App Store Connect.

Production Android requires a production-signed Play App Signing AAB. Production iOS requires a separately signed archive/IPA. EAS projects must be linked and both developer accounts, privacy/legal disclosures, icons/screenshots, review accounts and store reviews remain outstanding. The privacy page is a working draft, not the approved store policy.

## Website handoffs that remain intentional

The native app does not silently redirect at startup. These user-initiated website links remain because the corresponding service or legal document is still owned by the website:

- User: privacy notice and Explore links for accommodation, tourism and events.
- Driver: driver registration/verification and the privacy notice.
- Both: sharing the official app information/download page.

Password recovery and account deletion stay inside the native apps. The duplicate account-deletion website shortcut has been removed. The mobile navigation CI allowlist checks the remaining website-opening calls, so adding another handoff requires an explicit reviewed change.

## Requirements and commands

Node.js 22.13+, pnpm 10, Android SDK for local Android builds and macOS/Xcode for local iOS builds. From this directory:

- `pnpm install`
- `pnpm user:start` or `pnpm driver:start`
- `pnpm user:typecheck` and `pnpm driver:typecheck`

Set `EXPO_PUBLIC_API_BASE_URL` to the approved HTTPS API base URL. Never put secrets in `EXPO_PUBLIC` variables.

## App identities

| Product | Production Android package | Production iOS bundle ID | Scheme |
|---|---|---|---|
| User | `space.pamoja.afcon360.user` | `space.pamoja.afcon360.user` | `afcon360` |
| Driver | `space.pamoja.afcon360.driver` | `space.pamoja.afcon360.driver` | `afcon360-driver` |

Preview builds add `.preview` to each app's platform identifier and use a separate URL scheme. User and Driver production identities remain distinct.

Read `docs/backend-contracts.md`, `docs/api-inventory.md`, `docs/store-submission-checklist.md` and `AGENTS.md` before changing server contracts.

## Preview build distribution

The PR-capable workflow has read-only GitHub permissions, uses no stable signing secrets and does not publish Releases. It uploads run-scoped Android APK and manifest-audit artifacts for validation. Do not treat these CI artifacts as a permanent tester download URL or a production-signed update.

Never submit preview APKs to Google Play. iOS simulator builds are not distributable App Store/TestFlight packages.
