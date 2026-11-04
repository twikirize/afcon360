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
- [x] In-app sign-out and account-deletion controls exist. The current handler reauthenticates, revokes sessions/API keys, clears MFA/recovery/PIN credentials and anonymizes the primary User/Profile. It is not yet comprehensive: cross-domain PII snapshots in Events, Accommodation and Transport, active Wallet payment identities and balance/settlement handling remain unresolved.
- [x] Public web account-deletion initiation route exists at `/apps/delete-account`, alongside the in-app deletion control. End-to-end user testing and final retention-policy approval remain outstanding.
- [x] PR-safe User Android validation workflow can build or reuse a checksum-verified APK artifact; the current workflow does not publish a stable GitHub Release.
- [ ] Stable, in-place-updatable internal preview distribution is designed in a separate trusted workflow; current per-run CI signing keys are intentionally disposable and must not be stored as repository-level secrets.
- [ ] Live-like end-to-end tests for native login/MFA/refresh replay/revocation, rider booking commitment, driver offer assignment, trip lifecycle, Wallet settlement and deletion.
- [ ] Verify external and in-app deletion end-to-end across Identity/Profile, Events, Transport, Accommodation, Wallet/payment identities, uploads and processor copies. Test incorrect password, missing/invalid TOTP, protected-account rejection, active/upcoming service obligations, positive wallet balance, unsettled payment, retries and payment-recipient lookup after deletion. Current model review found direct PII snapshots outside Identity/Profile and active payment identities are not handled by the deletion service. Delete non-required data, restrict/time-limit legally required evidence, protect users' remaining funds and publish an approved category/legal-basis/retention schedule.
- [ ] Real-device testing on low-memory Android phones and supported iPhones, including permission denial, network loss and app upgrade.
- [x] Draft User and Driver store listing names, short descriptions and full descriptions prepared in `docs/store-listing-copy.md`.
- [ ] Final icons, splash screens, screenshots, store graphics and localized listing copy approved.

## Cross-platform compatibility evidence

- [x] User Android app passed install-and-launch checks on API 24, 29, 33 and 36 in [Run #53](https://github.com/twikirize/afcon360/actions/runs/41924848966).
- [ ] Driver Android API 24/29/33/36 matrix passes; Driver is intentionally outside the current validation phase.
- [ ] User and Driver iOS simulator build/install/launch checks pass with iOS 16.4 deployment target and current iOS 26 SDK; the current iOS job is disabled and has no passing evidence.
- [ ] Physical Android devices across older, mid-range and current OS releases pass fresh install and same-key update tests.
- [ ] Physical iPhone/iPad devices on the minimum supported iOS release and current iOS release pass install, launch, permissions and update tests.
- [ ] Actual tested device models, OS versions, run links and failures are recorded before store submission.

## Android / Google Play

- [ ] Play Console account, legal developer identity, access roles and contact verified.
- [ ] User and Driver package IDs reserved in the intended Play Console account.
- [ ] Production signing key and Play App Signing configured. The internal preview signing key must remain separate from production signing.
- [ ] Production-signed AAB generated; preview APK is not a store binary.
- [ ] Generated target SDK verified as Android 16 / API 36 or higher. Google's published rule requires API 36+ for new app submissions and updates from 31 August 2026.
- [ ] Final store listing text and metadata approved; support URL, 512×512 icon, 1024×500 feature graphic and phone/tablet screenshots prepared.
- [ ] Approved privacy policy is live, public, non-editable and accessible globally; Data safety, App access, content rating, target audience, ads and permission declarations match the actual app and all included SDKs.
- [ ] Financial features declaration completed accurately in Play Console. Review whether the Wallet balance and ride-payment functionality constitutes mobile payments/digital-wallet functionality; do not select “no financial features” without confirming the feature set.
- [ ] Reviewer credentials/instructions tested for both customer and driver experiences.
- [ ] Financial-services declarations and any applicable payment policy requirements reviewed.
- [ ] Internal/closed testing, pre-launch report, device matrix and policy checks passed.
- [ ] Review accepted and official Play URLs verified before preview links are replaced.

## Native feature scope and reviewer access

The current User binary includes native sign-in/MFA, ride location search and fare quotation, payment-method selection and ride requests, ride activity, Wallet balance/status display and account controls. Accommodation, tourism and events launch the existing AFCON360 website in the system browser. Describe this accurately in screenshots, store copy and review notes; do not imply every service is a native screen or that payment capture occurs in the ride request flow.

For Apple review, the native ride and account experience must be clearly useful beyond a collection of website links. Keep the ride flow live, complete and testable, and provide a reviewer account with working MFA instructions or a full-featured demo mode. Apple requires a complete, functional submission and access to account-based features during review; Guideline 4.2 expects utility beyond a repackaged website.

## Apple App Store

- [ ] Apple Developer Program membership and App Store Connect access active.
- [ ] User and Driver bundle IDs registered under the correct Apple team.
- [ ] Distribution certificate, profiles and production signing configured.
- [ ] Signed IPA built and uploaded to TestFlight.
- [ ] Approved privacy policy URL linked inside both apps and in App Store Connect.
- [ ] App Privacy labels reflect actual data types, purposes, linkage and third-party processing.
- [ ] In-app and external web account deletion tested end-to-end across every data domain and processor. Current handler does not yet cover all direct-PII snapshots in Events, Accommodation and Transport, or active Wallet payment identities/account settlement. Verify erasure of non-required data, restricted/time-limited retention of legally required records, safe handling of positive balances and the approved published retention schedule.
- [ ] Location purpose text matches the foreground-only Driver behavior.
- [ ] App Review notes include working demo accounts and MFA instructions for both apps.
- [ ] Final descriptions, icons, screenshots, support URL, age rating, pricing and availability complete.
- [ ] TestFlight device testing passed, App Review accepted and official App Store URLs verified.

## Privacy, legal and operational sign-off

- [ ] Privacy notice approved by AFCON360's data controller/legal adviser for each launch jurisdiction. The current `/apps/privacy` page explicitly identifies itself as a working draft and is a Google Play / Apple submission blocker.
- [ ] Data controller identity/contact, lawful bases, data-subject rights and complaint channels confirmed for Uganda and every launch jurisdiction.
- [ ] Actual GEO/geocoding and Wallet/payment provider inventory, processing countries, contracts and cross-border safeguards confirmed.
- [ ] Retention periods for KYC/identity, security sessions, precise location, rides, Wallet and audit records approved and published.
- [ ] Support and safety escalation contacts published and tested.
- [ ] Signing-key custody, rollback, minimum supported app version and update cadence documented.

## GitHub Actions preview signing setup

The current PR-capable workflow uses a new ephemeral CI signing key per APK build, masks its password, has read-only token permissions and does not publish a Release. The downloaded APK is an Actions artifact; it is not guaranteed to accept an in-place update from a future artifact signed with a different temporary key.

Do **not** add the former `AFCON360_PREVIEW_KEYSTORE_*` values as repository-level Actions secrets. Remove those repository secrets if they exist. A same-repository pull request can propose edits to a PR-triggered workflow, so stable signing keys must not be accessible to that workflow.

If stable internal distribution becomes necessary, create a separate trusted release workflow that pull requests cannot modify and protect its signing key in a GitHub Environment with required approval and an allowlist of trusted release branches. Never use preview signing material for Google Play production signing.

See [the current preview-signing policy](preview-signing-setup.md).

## Distribution labels

- **Internal preview APK:** run-scoped GitHub Actions artifact for direct Android testing. The current PR workflow uses an ephemeral CI signing key; it is not a stable update channel and is not eligible for Play Console submission.
- **Google Play:** production-signed AAB distributed and updated by Play.
- **Apple App Store:** separately signed IPA reviewed and distributed by Apple.
- **Share URL:** canonical `https://www.pamoja.space/apps` page; official store listing URLs are added only after approval.

## Official references

- Google Play target API requirement: https://support.google.com/googleplay/android-developer/answer/11926878
- Apple App Review Guidelines: https://developer.apple.com/app-store/review/guidelines/
- Apple App Privacy Details: https://developer.apple.com/app-store/app-privacy-details/
- Expo APK build configuration: https://docs.expo.dev/build-reference/apk/
- Expo internal distribution: https://docs.expo.dev/build/internal-distribution/
