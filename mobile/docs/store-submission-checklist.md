# AFCON360 store submission checklist

Status is evidence-based. A green code/build check is not store approval.

## Code and architecture readiness

- [x] Separate User and Driver native packages with distinct Android application IDs and iOS bundle IDs.
- [x] Shared React Native foundation with strict TypeScript checks.
- [x] Native Identity authentication reuses the existing User, MFA, DeviceSession and audit models; no parallel user/role system.
- [x] Account closure revokes device/server sessions and personal API keys, erases active MFA/recovery/PIN secrets, disables login and scrubs direct profile identifiers while preserving legally controlled KYC/financial/audit records.
- [x] Short-lived access credentials, refresh rotation, reuse detection and device logout/revocation.
- [x] Production API client requires HTTPS and resolves current user/driver ownership server-side.
- [x] User ride flow uses GEO geocoding, signed Transport fare quotes, request-first ride creation and Wallet-certified payment options.
- [x] Ride request reference is distinct from a committed driver/vehicle assignment.
- [x] Driver readiness, offers, trip progression, foreground location and captured earnings use existing server services/records.
- [x] Driver location is foreground-only and only requested after explicit driver action; background tracking is not enabled.
- [x] Wallet amounts and payment state are server-provided; no client ledger or fare authority.
- [x] In-app sign-out and account deletion controls exist; the deletion handler revokes sessions/API keys, clears MFA/recovery/PIN credentials, anonymizes direct profile identifiers and retains only separately controlled KYC/financial/audit records as required.
- [x] Public web account-deletion initiation route exists at `/apps/delete-account`, alongside the in-app deletion control. End-to-end user testing and final retention-policy approval remain outstanding.
- [ ] Latest-head Android and iOS compatibility workflow passes for both User and Driver apps.
- [ ] Physical Android and iPhone/iPad acceptance completed on the supported device matrix.
- [ ] A separate trusted stable tester-distribution workflow is designed, reviewed and protected; the current PR workflow uses disposable CI-only signing.
- [ ] Live-like end-to-end tests for native login/MFA/refresh replay/revocation, rider booking commitment, driver offer assignment, trip lifecycle, Wallet settlement and deletion.
- [ ] Verify external deletion requests through web login, including incorrect password, missing/invalid TOTP, protected account rejection, and retained-record disclosure.
- [ ] Real-device testing on low-memory Android phones and supported iPhones, including permission denial, network loss and app upgrade.
- [x] Draft User and Driver store listing names, short descriptions and full descriptions prepared in `docs/store-listing-copy.md`.
- [ ] Final icons, splash screens, screenshots, store graphics and localized listing copy approved.

## Android / Google Play

- [ ] Play Console account, legal developer identity, access roles and contact verified.
- [ ] User and Driver package IDs reserved in the intended Play Console account.
- [ ] Production signing key and Play App Signing configured. The internal preview signing key must remain separate from production signing.
- [ ] Production-signed AAB generated; preview APK is not a store binary.
- [ ] Generated target SDK verified as Android 16 / API 36 or higher. Google's published rule requires API 36+ for new app submissions and updates from 31 August 2026.
- [ ] Final store listing text and metadata approved; support URL, 512×512 icon, 1024×500 feature graphic and phone/tablet screenshots prepared.
- [ ] Approved privacy policy, Data safety declaration, App access, content rating, target audience, ads and permission declarations completed.
- [ ] Reviewer credentials/instructions tested for both customer and driver experiences.
- [ ] Financial-services declarations and any applicable payment policy requirements reviewed.
- [ ] Internal/closed testing, pre-launch report, device matrix and policy checks passed.
- [ ] Review accepted and official Play URLs verified before preview links are replaced.

## Apple App Store

- [ ] Apple Developer Program membership and App Store Connect access active.
- [ ] User and Driver bundle IDs registered under the correct Apple team.
- [ ] Distribution certificate, profiles and production signing configured.
- [ ] Signed IPA built and uploaded to TestFlight.
- [ ] Approved privacy policy URL linked inside both apps and in App Store Connect.
- [ ] App Privacy labels reflect actual data types, purposes, linkage and third-party processing.
- [ ] In-app account deletion tested end-to-end.
- [ ] Location purpose text matches the foreground-only Driver behavior.
- [ ] App Review notes include working demo accounts and MFA instructions for both apps.
- [ ] Final descriptions, icons, screenshots, support URL, age rating, pricing and availability complete.
- [ ] TestFlight device testing passed, App Review accepted and official App Store URLs verified.

## Privacy, legal and operational sign-off

- [ ] Privacy notice approved by AFCON360's data controller/legal adviser for each launch jurisdiction; current `/apps/privacy` page is a working draft only.
- [ ] Data controller identity/contact, lawful bases, data-subject rights and complaint channels confirmed for Uganda and every launch jurisdiction.
- [ ] Actual GEO/geocoding and Wallet/payment provider inventory, processing countries, contracts and cross-border safeguards confirmed.
- [ ] Retention periods for KYC/identity, security sessions, precise location, rides, Wallet and audit records approved and published.
- [ ] Support and safety escalation contacts published and tested.
- [ ] Signing-key custody, rollback, minimum supported app version and update cadence documented.

## GitHub Actions preview signing setup

The current PR-capable workflow generates a temporary signing key inside each APK build, masks its password, uses read-only token permissions and does not publish a GitHub Release. Downloaded APKs are run-scoped Actions artifacts, not a stable update channel.

Do **not** add the former `AFCON360_PREVIEW_KEYSTORE_*` values as repository-level Actions secrets for this workflow. If they were configured earlier, a repository owner should review and remove any that are no longer needed under **Settings → Secrets and variables → Actions**. This PR has not changed repository secret settings.

A future stable internal distribution channel must use a separate trusted workflow that pull requests cannot modify and a protected GitHub Environment with required approval and a trusted-branch allowlist. The preview key must never be the Google Play production signing key.

## Distribution labels

- **Internal preview APK:** run-scoped GitHub Actions artifact for direct Android testing. The current PR workflow uses an ephemeral CI signing key, does not publish a GitHub Release and is not eligible for Play Console submission.
- **Google Play:** production-signed AAB distributed and updated by Play.
- **Apple App Store:** separately signed IPA reviewed and distributed by Apple.
- **Share URL:** canonical `https://www.pamoja.space/apps` page; official store listing URLs are added only after approval.

## Official references

- Google Play target API requirement: https://support.google.com/googleplay/android-developer/answer/11926878
- Apple App Review Guidelines: https://developer.apple.com/app-store/review/guidelines/
- Apple App Privacy Details: https://developer.apple.com/app-store/app-privacy-details/
- Expo APK build configuration: https://docs.expo.dev/build-reference/apk/
- Expo internal distribution: https://docs.expo.dev/build/internal-distribution/
