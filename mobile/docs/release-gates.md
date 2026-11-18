# Mobile release gates

A release advances only when evidence for its gate is recorded. CI and source inspection do not substitute for live-like service tests or physical-device acceptance.

## Gate 0 — repository and bundle checks

- [ ] Latest native branch head installs the pnpm workspace and passes Expo SDK compatibility checks for User and Driver.
- [ ] Latest native branch head passes strict TypeScript checks for both apps.
- [ ] User and Driver Metro bundles export for Android and iOS.
- [ ] Flask mobile API modules compile and native-app website templates parse in CI.
- [ ] Expo Doctor and full native project diagnostics reviewed.
- [ ] Android development builds install, launch and render the expected native app identity and sign-in action on physical Android devices.
- [ ] iOS development builds install and launch on a real iPhone.
- [ ] Final icons, splash screens, privacy strings and brand artwork approved.

## Gate 1 — backend implementation

- [x] Native password sign-in reuses canonical Auth credential and lockout logic.
- [x] TOTP and backup-code MFA verification uses existing Auth routines. Native SMS challenge UI is wired to the canonical server response, but the server only sends SMS to a verified E.164 phone when a real provider is configured; real provider delivery must be tested before release.
- [x] Short-lived bearer access tokens, one-time refresh rotation, replay detection, device revocation, logout and /me are implemented.
- [x] Bearer requests pin Flask-Login identity to the token owner; protected operations resolve the user/driver from server-side records.
- [x] User place search, signed fare discovery, Wallet-certified payment options and request-first ride creation use GEO/Transport/Wallet services.
- [x] Ride tracking reveals driver/vehicle details only after server-side assignment.
- [x] Driver readiness, offer handling, trip transitions, foreground location, cash receipt and captured earnings use existing Transport/Wallet services.
- [x] Native Wallet balance/history, PIN, recipient resolution, same-currency transfer and verified-deposit contracts are merged into main.
- [ ] Native withdrawals remain disabled pending the separate clearing/journal decision and provider acceptance; cross-currency transfers and generic refunds are not available.
- [ ] Native accommodation API PR #45 and event/free-ticket API PR #46 remain draft server work; paid tickets are deliberately unavailable.
- [x] Account closure is shared by web and mobile; it reauthenticates, checks open Transport obligations, revokes sessions/API keys, invalidates MFA/recovery/PIN material and anonymizes direct identifiers.
- [x] Domain response/authorization inventory is documented in `docs/backend-contracts.md` and `docs/api-inventory.md`.
- [ ] Selected request-first PostgreSQL regression workflow passed on the final native branch head.
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

## Gate 3 — direct Android preview validation

- [ ] Both User and Driver APKs build from the same native branch head.
- [ ] Each APK passes package identity, signature, target API, minimum SDK, backup-policy and payload checks.
- [ ] Both APKs install, stay running and render the expected app identity and primary sign-in action on Android API 24, 29, 33 and 36 emulators.
- [ ] Both APK manifest audits confirm no legacy broad-storage or overlay permissions and no debuggable/cleartext configuration.
- [ ] Latest-run APK and manifest audit artifacts are available with build provenance and SHA-256 checksums.
- [ ] Physical Android installation and driver-location permission tests pass.
- [ ] Preview APKs remain labelled as internal test builds, not Play Store releases.

The emulator smoke test checks the Android UI hierarchy for the correct User/Driver identity and primary sign-in action after launch. It does not submit credentials, create accounts or write to the production backend. The navigation contract requires approved external website handoffs to be explicitly labelled; password recovery and account deletion stay in native screens.

The PR-capable validation workflow uses disposable CI signing keys and read-only GitHub permissions. It does not publish a GitHub Release or use permanent signing secrets. Every run uses a different temporary signature; a new test APK may require uninstalling the previous preview before installation. A stable tester-distribution release needs a separate trusted workflow and protected signing environment.

## Exact-build and reinstall behavior

The current CI APKs are disposable-key validation artifacts, not an in-place update channel. The public `/download` page currently points at fixed GitHub Release asset URLs and does not expose a verified installed-build comparison. Do not claim that a phone is up to date based only on a download click, a browser cookie, a version label or a locally cached value.

Before a tester-facing install/reinstall status is enabled:

- [ ] Every published User and Driver APK has a manifest containing app/package ID, release channel, display version, monotonic Android `versionCode`, immutable `build_id`, source commit, workflow run/attempt, APK SHA-256, signing-certificate SHA-256 and exact asset URL.
- [ ] The immutable `build_id` is embedded in the installed app at build time and is also published in the manifest. Build identity must distinguish different APK artifacts even when the display version is unchanged.
- [ ] Every distinct installable APK receives a strictly higher Android `versionCode` for that package/channel. Do not reuse a version code for a different artifact.
- [ ] A trusted release pipeline signs each tester-distribution APK with the same protected signing key for that package/channel. PR/CI disposable keys must never be used for tester distribution or represented as upgrade-compatible.
- [ ] The app compares its embedded installed `build_id` with the authoritative published manifest. The public download page may only display an installed-build state when that verified identity is supplied by the app or another trusted mechanism.
- [ ] When installed and available `build_id` values match, show **“You’re up to date”** and do not show an Update action. A secondary **“Reinstall this same build”** action may be offered only after a clear confirmation.
- [ ] When the available build differs, show **“New build available”** for a changed build with the same display version, or **“New version available”** when the display version changes. Only then may the app describe the action as an update.
- [ ] The app never downloads or reinstalls automatically. A reinstall requires an explicit user confirmation; the confirmation must identify the exact build/version.
- [ ] Tests cover exact-build match, different build/same display version, higher version, stale/unavailable manifest, invalid package/channel, checksum mismatch and signing-certificate mismatch.

The Android system package-installer dialog is controlled by Android and may use its own wording. AFCON360 must use the states and wording above in its own UI; it cannot rename the operating system's installer dialog. Until these gates pass, keep the existing preview link labelled **Download APK** and do not describe it as an update mechanism.

## Gate 4 — iOS simulator and App Store

- [ ] Both User and Driver iOS projects prebuild and pass Expo dependency compatibility.
- [ ] Both iOS apps build, install and launch on the current iOS 26.4 simulator.
- [ ] Both generated app bundles use the intended bundle IDs and iOS 16.4 deployment minimum.
- [ ] Physical iPhone/iPad installation, permission prompts, accessibility and upgrade paths tested.
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

Simulator CI does not create a signed IPA, submit a build to App Store Connect or establish store approval.

## Gate 5 — Google Play

- [ ] Play Console developer account, legal developer identity, access roles and contact verified.
- [ ] User and Driver application IDs reserved in the intended Play Console account.
- [ ] Production signing key and Play App Signing configured; signed AAB generated.
- [ ] Target SDK verified at API 36 or higher in the production AAB.
- [ ] App names, short/full descriptions, support URL, 512×512 icons, 1024×500 feature graphics and phone/tablet screenshots prepared.
- [ ] Approved privacy policy and Data safety declaration match actual app data, SDKs and processors.
- [ ] App access/reviewer instructions include test credentials and MFA steps for both apps.
- [ ] Content rating, target audience, ads, permissions and any financial-services declarations completed truthfully.
- [ ] In-app and web account-deletion experience tested; Play deletion-policy requirements and retained-record disclosures reviewed.
- [ ] Internal/closed testing, pre-launch report, device matrix and policy checks passed.
- [ ] Review accepted and official Play URLs verified before replacing preview status.

## Legal and operational sign-off

- [ ] Privacy notice approved by AFCON360's data controller/legal adviser for each launch jurisdiction. Current `/apps/privacy` page is a working draft only.
- [ ] Provider inventory, processing countries, lawful bases and cross-border safeguards confirmed.
- [ ] Retention periods for identity/KYC, sessions, precise location, trips, Wallet and audit records approved and published.
- [ ] Support and safety escalation contacts published and tested.
- [ ] Signing-key custody, rollback, minimum supported app version and update cadence documented.

Preview APK builds are for internal Android validation only. Production Google Play requires a production-signed AAB; iOS requires a separately signed archive/IPA and App Store review.
