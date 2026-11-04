# Mobile release gates

A release advances only when the listed evidence exists. Code presence, passing static CI, and a preview APK are not the same as a signed store release.

## Gate 0 — repository and bundle checks

- [x] SDK 58 workspace installs with pinned pnpm in GitHub Actions.
- [x] Both apps pass Expo SDK dependency compatibility and strict TypeScript checks.
- [x] Metro exports succeed for User and Driver on Android and iOS.
- [x] Flask mobile API modules compile and the mobile website templates parse in CI.
- [ ] Android preview APKs install and run on physical devices.
- [ ] iOS development/production build installs on a real iPhone.
- [ ] Final icons, splash screens, privacy strings and brand assets approved.

## Gate 1 — backend integration

- [x] Native sign-in reuses AFCON360 Identity password/MFA verification and existing device/server session records.
- [x] Short-lived Bearer access tokens, rotating refresh tokens, reuse detection and device logout/revocation are implemented.
- [x] Server-side account and driver-profile ownership checks guard all protected mobile endpoints.
- [x] User ride flow uses canonical GEO search evidence, signed Transport fare quote, request-first service and Wallet-certified payment options.
- [x] Request tracking separates an intent/reference from committed driver and vehicle assignment.
- [x] Driver readiness, offers, trip progression, foreground location and earnings use existing Transport services and records.
- [x] Wallet balances and payment states come from Wallet; the app does not create its own ledger or payment authority.
- [x] Public web account deletion and native account deletion call the same shared service; session, API-key and MFA material is revoked or cleared, profile identifiers are anonymized, and retained records are restricted to legally required operational evidence.
- [x] Driver is taken offline on account closure; deletion is refused while ride search, assigned trip or cash receipt work remains open.
- [ ] Live-like end-to-end tests for native login/MFA/refresh replay/revocation, rider booking commitment, driver offer assignment, trip lifecycle, Wallet settlement, cash receipt and deletion.
- [ ] Push notifications and revocable device-token registration. Current offers are polled; no push-delivery channel is claimed.

## Gate 2 — device and safety testing

- [ ] Small Android phones, larger Android phones and tablets tested.
- [ ] Current iPhone sizes and supported iOS versions tested.
- [ ] Permission denied, limited, revoked and restored states are handled on physical devices.
- [ ] Network loss, app restart, expired sessions, refresh replay and concurrent requests tested.
- [ ] Driver GPS freshness, battery and foreground/background behavior tested.
- [ ] Accessibility, dynamic text, safe areas and light/dark appearance tested.
- [ ] No secrets, tokens, private data or sensitive diagnostics appear in logs.

## Gate 3 — build accounts and signing

- [x] Separate User and Driver Android application IDs and iOS bundle identifiers are configured.
- [x] EAS internal, APK-share and store-distribution profiles are configured in both apps.
- [ ] EAS project IDs linked to the correct AFCON360 owner/team.
- [ ] Apple Developer account, App Store Connect access, signing certificate and provisioning profiles available.
- [ ] Google Play Console account, legal developer identity and app records verified.
- [ ] Production Android signing key and Play App Signing configured.
- [ ] Production-signed Android AAB generated.
- [ ] Signed iOS archive/IPA generated and uploaded to TestFlight.
- [ ] Store listing metadata, support details and review credentials finalized.

## Gate 4 — direct APK sharing

- [x] Website /apps offers separate User and Driver APK download and share-link controls.
- [x] Native Account screens can share the app landing URL and the corresponding APK URL.
- [x] APK job builds User and Driver in parallel and checks the resulting package ID, API level, signature and DEX payload before publishing.
- [x] Publishing guard prevents a build from replacing the public preview when its commit is no longer the branch head.
- [ ] Add the four stable internal preview signing secrets to GitHub Actions as documented in the store-submission checklist.
- [ ] Both APK builds complete with the stable key and SHA-256 checksums.
- [ ] The public GitHub Release mobile-preview contains both APK files and checksum file.
- [ ] Download URLs return HTTP 200; install and in-place upgrade are verified on Android devices.
- [ ] The /apps page is deployed to production and tested over HTTPS.

## Gate 5 — Google Play submission

- [ ] Play Console developer account, legal identity, access roles and contact verified.
- [ ] Both application IDs reserved in the intended Play Console account.
- [ ] Production signing key and Play App Signing configured; signed AABs generated.
- [ ] Final target SDK verified in each AAB as Android 16 / API 36 or higher.
- [ ] Listing text, support URL, 512×512 icon, 1024×500 feature graphic and device screenshots prepared.
- [ ] Approved privacy policy, Data safety, App access, content rating, target audience, ads and permissions declarations completed.
- [ ] Reviewer access/demo credentials tested for both customer and driver experiences.
- [ ] Account-deletion web URL entered in Play Console; in-app and external deletion tested end to end.
- [ ] Internal/closed testing, pre-launch report, device matrix and policy checks passed.
- [ ] Review accepted and official store URLs verified before replacing preview status.

## Gate 6 — Apple App Store submission

- [ ] Apple Developer Program and App Store Connect access active.
- [ ] User and Driver bundle IDs registered under the correct Apple team.
- [ ] Distribution certificate, profiles and production signing configured.
- [ ] Signed IPA uploaded to TestFlight and tested on physical devices.
- [ ] Approved privacy policy linked in both apps and in App Store Connect.
- [ ] App Privacy disclosures match actual data types, purposes, linkage and processors.
- [ ] In-app account deletion tested end to end, including reauthentication and lawful-retention messaging.
- [ ] Location purpose strings match the foreground-only Driver location behavior.
- [ ] App Review notes include working User and Driver demo accounts and MFA instructions.
- [ ] Icons, screenshots, descriptions, support URL, age rating, pricing and availability completed.
- [ ] TestFlight device testing passed; App Review accepted; official listing URLs verified.

## Legal and operational sign-off

- [ ] Privacy notice approved by AFCON360's data controller/legal adviser for every launch jurisdiction.
- [ ] Data controller identity/contact, lawful bases, data-subject rights and complaint routes confirmed.
- [ ] Actual GEO/geocoding and Wallet/payment provider inventory, processing countries, contracts and cross-border safeguards confirmed.
- [ ] Retention periods for identity/KYC, sessions, precise location, rides, Wallet and audit records approved and published.
- [ ] Support and safety escalation contacts published and tested.
- [ ] Signing-key custody, rollback, minimum supported app version and update cadence documented.

The internal preview APKs are only an Android tester-distribution path. They are not Play Store binaries. Production Android needs signed AABs; iOS distribution needs Apple's signed IPA and review.
