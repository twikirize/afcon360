# AFCON360 Native Mobile

Two separate native products share one React Native foundation:

- **AFCON360 User** — customers, riders and fans.
- **AFCON360 Driver** — approved drivers and transport operators.

Both use Expo SDK 58, React Native 0.88.1, React 19.3 and TypeScript 6. Flask remains the system of record. Mobile clients use HTTPS APIs and never connect directly to PostgreSQL.

## Implemented in this branch

- Separate Android application IDs and iOS bundle IDs.
- Shared native UI, HTTPS API client and operating-system SecureStore.
- Native password login, TOTP/backup-code MFA, 10-minute access tokens, 30-day rotating refresh credentials and device logout/revocation. SMS MFA is intentionally unsupported until the existing Auth verifier supports it.
- User ride flow: GEO search, signed fare quotes, Wallet-certified payment methods, request-first Transport creation, activity and tracking.
- Driver flow: go-live checklist, offer polling/accept/decline, trip progress, foreground driver-initiated GPS, cash receipt confirmation and currency-separated captured earnings.
- In-app account closure plus the web deletion resource at `/apps/delete-account`.
- Website app/share page at `/apps`, preview APK pipeline and Android/iOS EAS profiles.

## What is still a release gate

The branch is not merged or deployed. The User Android APK was built and verified in Run #48, then installed and launched successfully on Android API 24, 29, 33 and 36 in Run #53. This is emulator evidence only: live-like end-to-end and physical-device acceptance remain outstanding. The current PR workflow uses a disposable CI signing key and uploads an Actions artifact; it does not publish a stable preview Release.

Production Android requires a Play App Signing AAB. iOS requires a signed App Store/TestFlight archive. EAS projects must be linked and both developer accounts, privacy/legal disclosures, icons/screenshots, review accounts and store reviews remain outstanding. The privacy page is a working draft, not the approved store policy.

## One shared source system and supported platforms

AFCON360 is maintained as one Git repository and one React Native/Expo workspace. User and Driver remain separate products, but common UI, API, authentication, session, wallet and domain logic belongs in `mobile/packages/` and is consumed by both apps under `mobile/apps/`. Platform-specific native permissions and operating-system integrations remain in each app's Expo config.

The same source tree produces different signed deliverables:
- Google Play: production Android App Bundle (`.aab`) for each app.
- Direct Android testing: internally signed preview APK (`.apk`) for each app; never submit these preview APKs to Play.
- Apple App Store/TestFlight: separately signed iOS archive/IPA for each app.

There is no single Android/iOS binary. The source, shared packages, API contracts, app behavior and release version are kept together; each store receives its platform-native output and platform-specific signing.

## Supported operating-system baseline

The current Expo SDK 58 baseline is Android 7.0+ (API 24) and iOS 16.4+. Android builds compile with SDK 37 and target API 36. CI has verified the User Android app on API 24, 29, 33 and 36. Driver Android and both iOS simulator matrices are not currently enabled; physical-device testing remains required before release.

See [platform compatibility and release matrix](docs/platform-compatibility.md) for the current policy and evidence gates.

## Requirements and commands

Node.js 22.13+, pnpm 10, Android SDK for local Android builds and macOS/Xcode for local iOS builds. From this directory:

- `pnpm install`
- `pnpm user:start` or `pnpm driver:start`
- `pnpm user:typecheck` and `pnpm driver:typecheck`

Set `EXPO_PUBLIC_API_BASE_URL` to the approved HTTPS API base URL. Never put secrets in `EXPO_PUBLIC` variables.

## App identities

| Product | Android package | iOS bundle ID | Scheme |
|---|---|---|---|
| User | `space.pamoja.afcon360.user` | `space.pamoja.afcon360.user` | `afcon360` |
| Driver | `space.pamoja.afcon360.driver` | `space.pamoja.afcon360.driver` | `afcon360-driver` |

Read `docs/backend-contracts.md`, `docs/api-inventory.md`, `docs/store-submission-checklist.md` and `AGENTS.md` before changing server contracts.

## Direct APK sharing

The current pull-request workflow validates only the User Android APK. It uses an ephemeral CI key, uploads a run-scoped Actions artifact and does not publish or update the `mobile-preview` Release. Never submit a preview APK to Play Console.


### Preview APK signing

The current PR-capable workflow generates a disposable CI signing key inside the signing step, masks its password, has read-only GitHub token permissions and does not publish a Release. Do not add stable preview-key credentials as repository-level Actions secrets. If those old secrets exist, remove them. Any future stable tester distribution must use a separate trusted workflow and protected GitHub Environment, not a PR-editable workflow.

See [the current preview-signing policy](docs/preview-signing-setup.md).
