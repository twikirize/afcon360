# Mobile release gates

A release advances only when evidence for its gate is recorded. CI and source inspection do not substitute for live-like service tests or physical-device acceptance.

## Gate 0 — repository and bundle checks

- [x] pnpm workspace installs and both apps pass Expo SDK compatibility checks.
- [x] Both apps pass strict TypeScript checks.
- [x] User and Driver Metro bundles export for Android and iOS.
- [x] Flask mobile API modules compile and native-app website templates parse in CI.
- [ ] Expo Doctor and full native project diagnostics reviewed.
- [ ] Android development builds install and launch on physical Android devices.
- [ ] iOS development builds install and launch on a real iPhone.
- [ ] Final icons, splash screens, privacy strings and brand artwork approved.

## Gate 1 — backend implementation

- [x] Native password sign-in reuses canonical Auth credential and lockout logic.
- [x] TOTP and backup-code MFA verification uses existing Auth routines. SMS MFA remains unsupported until the canonical Auth verifier supports it.
- [x] Short-lived bearer access tokens, one-time refresh rotation, replay detection, device revocation, logout and /me are implemented.
- [x] Bearer requests pin Flask-Login identity to the token owner; protected operations resolve the user/driver from server-side records.
- [x] User place search, signed fare discovery, Wallet-certified payment options and request-first ride creation use GEO/Transport/Wallet services.
- [x] Ride tracking reveals driver/vehicle details only after server-side assignment.
- [x] Driver readiness, offer handling, trip transitions, foreground location, cash receipt and captured earnings use existing Transport/Wallet services.
- [x] Account closure is shared by web and mobile; it reauthenticates, checks open Transport obligations, revokes sessions/API keys, invalidates MFA/recovery/PIN material and anonymizes direct identifiers.
- [x] Domain response/authorization inventory is documented in `docs/backend-contracts.md` and `docs/api-inventory.md`.
- [x] Selected request-first PostgreSQL regression workflow passed on the previous backend commit; rerun on this final consolidation commit before merge.
- [ ] Live-like end-to-end tests for native login/MFA/refresh replay/revocation, rider booking, driver offer assignment, trip progression, Wallet settlement and account deletion on the final branch head.
- [ ] Dedicated tests for bearer-vs-cookie identity confusion, active-trip deletion guard and refresh-token preservation during 5xx/network failures.
- [ ] Native Wallet deposit, withdrawal, transfer, transaction history, PIN and refund flows. These remain deliberately unimplemented.
- [ ] Push notifications/APNs/FCM registration and live trip updates.
- [ ] Native accommodation, ticket/event and tourism booking workflows.

## Gate 2 — device and safety testing

- [ ] Small Android phones, larger Android phones and tablets tested.
- [ ] Current iPhone sizes and supported iOS versions tested.
- [ ] Permission denied, limited, revoked and restored states are handled.
- [ ] Network loss, app restart, expired sessions, concurrent refresh and app-upgrade paths tested.
- [ ] Driver GPS freshness, battery and foreground/background behavior tested. Current release is foreground-only; continuous/background location is not enabled.
- [ ] Accessibility, dynamic text, safe areas and light/dark appearance tested.
- [ ] No secrets, tokens, private data or sensitive diagnostics appear in logs.

## Gate 3 — direct APK testing and distribution

- [x] Current PR-safe workflow uses read-only GitHub token permissions, no stable signing-secret references, no publishing job and an ephemeral CI signing key.
- [x] User APK package identity, minSdk 24, targetSdk 36, v2/v3 signature, DEX payload and packaged `allowBackup=false` were verified in Run #48.
- [x] The same checksum-verified User APK installed and launched on Android API 24, 29, 33 and 36 in [Run #53](https://github.com/twikirize/afcon360/actions/runs/41924848966).
- [ ] Rebuild after the signing-password masking change and inspect logs to confirm no ephemeral credential is exposed. A run that reuses the existing APK does not execute a fresh build.
- [ ] Driver Android matrix and Driver APK build pass.
- [ ] Physical Android device install, app update, login and network tests pass.
- [ ] Stable internal distribution is designed in a separate trusted workflow if needed; do not add signing keys to PR-accessible repository secrets.
- [ ] Preview APK is clearly labelled as an internal test build, not a Play Store or iPhone installer.

## Gate 4 — Google Play

- [ ] Play Console developer account, legal developer identity, access roles and contact verified.
- [ ] User and Driver application IDs reserved in the intended Play Console account.
- [ ] Production signing key and Play App Signing configured; signed AAB generated.
- [ ] Target SDK verified at API 36 or higher in the production AAB.
- [ ] App names, short/full descriptions, support URL, 512×512 icons, 1024×500 feature graphics and phone/tablet screenshots prepared.
- [ ] Approved, globally accessible privacy policy and Data safety declaration match actual data, SDKs, processors, retention and deletion practices. The current privacy page is explicitly a working draft and blocks store submission.
- [ ] App access/reviewer instructions include test credentials and MFA steps for both apps.
- [ ] Content rating, target audience, ads, permissions and Play Financial features declaration completed truthfully; assess Wallet and ride-payment capabilities rather than assuming no financial features.
- [ ] In-app and external web account deletion tested end-to-end; verify deletion of data not required to be retained and document retained categories, legal grounds and exact retention periods.
- [ ] Internal/closed testing, pre-launch report, device matrix and policy checks passed.
- [ ] Review accepted and official Play URLs verified before replacing preview status.

## Gate 5 — Apple App Store

- [ ] Apple Developer Program and App Store Connect access active.
- [ ] User and Driver bundle IDs registered under the correct Apple team.
- [ ] Distribution certificates/profiles and production signing configured.
- [ ] Signed iOS archive/IPA built and uploaded to TestFlight.
- [ ] Approved privacy policy linked inside both apps and in App Store Connect.
- [ ] App Privacy disclosures match actual data types, purposes, linkage and third-party processors.
- [ ] In-app account deletion tested end-to-end, including any outstanding financial or legal retention notice.
- [ ] Location purpose strings match foreground-only Driver behavior.
- [ ] App Review notes include working User and Driver demo accounts/instructions, including MFA.
- [ ] Icons, screenshots, descriptions, support URL, age rating, pricing and availability complete.
- [ ] TestFlight physical-device acceptance passed, App Review accepted and official listing URLs verified.

## Legal and operational sign-off

- [ ] Privacy notice approved by AFCON360's data controller/legal adviser for each launch jurisdiction. Current `/apps/privacy` page is a working draft only.
- [ ] Provider inventory, processing countries, lawful bases and cross-border safeguards confirmed.
- [ ] Retention periods for identity/KYC, sessions, precise location, trips, Wallet and audit records approved and published.
- [ ] Support and safety escalation contacts published and tested.
- [ ] Signing-key custody, rollback, minimum supported app version and update cadence documented.

Preview APK builds are for internal Android testers only. Production Google Play requires a production-signed AAB; iOS requires a separately signed archive/IPA and App Store review.
