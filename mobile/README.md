# AFCON360 Native Mobile

Two separate native products share one React Native foundation:

- **AFCON360 User** — customers, riders and fans.
- **AFCON360 Driver** — approved drivers and transport operators.

Both use Expo SDK 58, React Native 0.88.1, React 19.3 and TypeScript 6. Flask remains the system of record. Mobile clients use HTTPS APIs and never connect directly to PostgreSQL.

## Implemented in this branch

- Separate Android application IDs and iOS bundle IDs.
- Shared native UI, HTTPS API client and operating-system SecureStore.
- Native password login, TOTP/backup-code MFA, 10-minute access tokens, 30-day rotating refresh credentials and device logout/revocation.\n- In-app password recovery using a one-time email code, followed by server-validated password replacement and session revocation. SMS MFA is intentionally unsupported until the existing Auth verifier supports it.
- User ride flow: GEO search, signed fare quotes, Wallet-certified payment methods, request-first Transport creation, activity and tracking.
- Driver flow: go-live checklist, offer polling/accept/decline, trip progress, foreground driver-initiated GPS, cash receipt confirmation and currency-separated captured earnings.
- In-app account closure plus the web deletion resource at `/apps/delete-account`.
- Website app/share page at `/apps`, preview APK pipeline and Android/iOS EAS profiles.

## What is still a release gate

The branch is not merged or deployed. No live-like end-to-end run or physical-device acceptance has been completed. The Android internal preview build must finish and its package/target SDK/signature be verified before APK links can be considered live. Direct APKs are signed with a dedicated internal preview key, not the production Play App Signing key.

Production Android requires a Play App Signing AAB. iOS requires a signed App Store/TestFlight archive. EAS projects must be linked and both developer accounts, privacy/legal disclosures, icons/screenshots, review accounts and store reviews remain outstanding. The privacy page is a working draft, not the approved store policy.

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

The workflow publishes two internally preview-key-signed Android APKs to the GitHub prerelease named `mobile-preview` only after both standalone Android builds, package identity, target API and signature checks pass. The website `/apps` exposes the download/share links. Never submit these APKs to Play Console.


### Preview APK signing secret

The GitHub Actions APK workflow intentionally fails closed until a stable test keystore is configured. Follow `docs/android-preview-signing-setup.md`, then add the four encrypted repository secrets documented in `docs/store-submission-checklist.md`. The signing keystore is never committed to this public repository and must be backed up securely. This test key is distinct from the production Play App Signing key.


For Windows PowerShell instructions to create and add the stable internal preview signing key, see docs/preview-signing-setup.md. Do not add the keystore or password to Git.
