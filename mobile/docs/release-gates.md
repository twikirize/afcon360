# Mobile release gates

A release advances only when evidence for its gate is recorded.

## Gate 0 — repository and local build

- [ ] SDK 58 workspace installs with pnpm.
- [ ] Both apps pass Expo SDK compatibility checks, Expo Doctor and TypeScript checks.
- [ ] Metro exports succeed for both Android and iOS bundles for both apps.
- [ ] Android development builds install on a physical device.
- [ ] iOS development builds install on a real iPhone.
- [ ] Icons, splash screens, privacy strings and brand assets are approved.

## Gate 1 — backend integration

- [ ] Native sign-in, refresh rotation, logout/revocation and /me are implemented and security-tested.
- [ ] Role/context and driver ownership are enforced server-side.
- [ ] Each screen endpoint has a documented response schema and authorization policy.
- [ ] Transport quote/booking/matching/trip lifecycle passes end-to-end tests.
- [ ] Wallet/payment/refund/earnings come from canonical server records.
- [ ] Notifications and device registration are implemented and revocable.

## Gate 2 — device and safety testing

- [ ] Small Android phones, larger Android phones and tablets tested.
- [ ] Current iPhone sizes and supported iOS versions tested.
- [ ] Permission denied, limited, revoked and restored states are handled.
- [ ] Network loss, app restart, expired sessions and concurrent requests tested.
- [ ] Driver GPS freshness, battery and foreground/background behavior tested.
- [ ] Accessibility, dynamic text, safe areas and light/dark appearance tested.
- [ ] No secrets, tokens, private data or sensitive diagnostics appear in logs.

## Gate 3 — store and production release

- [ ] Google Play developer account, signing and listing metadata are available.
- [ ] Apple Developer account, App Store Connect access, signing and listing metadata are available.
- [ ] Privacy policy, data safety and permission declarations are accurate.
- [ ] EAS projects are created and linked independently for User and Driver.
- [ ] Store builds pass internal testing and review.
- [ ] Verified Play Store and App Store URLs replace status labels on /apps.
- [ ] Production release has rollback and version-support plans.

Creating this scaffold does not imply store submission or production deployment.

## Gate 4 — direct APK sharing

- [ ] User and Driver Android preview APKs built and published from the controlled release workflow.
- [ ] APK download URLs return HTTP 200 and package identities are verified.
- [ ] SHA-256 checksums are published with both APKs.
- [ ] Download/share page labels previews as test builds, not production/store binaries.
- [ ] No preview APK is presented as an iPhone installer or a Play Store release.

## Gate 5 — Play Store submission

- [ ] Play Console developer account, legal identity and access roles verified.
- [ ] Both application IDs reserved in the intended Play Console account.
- [ ] Production signing key and Play App Signing configured; signed AAB generated.
- [ ] Android target SDK verified at API 36 or higher for new submissions under the currently published requirement.
- [ ] Listing text, support URL, 512×512 icon, 1024×500 feature graphic and device screenshots prepared.
- [ ] Approved privacy policy, Data safety, App access, content rating, target audience, ads and permissions declarations completed.
- [ ] Reviewer access/demo credentials tested.
- [ ] Internal/closed track, pre-launch report, device matrix and policy checks passed.
- [ ] Review accepted and official store URL verified before replacing preview status.

## Gate 6 — Apple App Store submission

- [ ] Apple Developer Program and App Store Connect access.
- [ ] Bundle IDs registered and distribution signing configured.
- [ ] Signed IPA uploaded to TestFlight and tested on physical devices.
- [ ] Approved privacy policy linked inside both apps and in App Store Connect.
- [ ] App Privacy disclosures match actual data types, purposes, linkage and processors.
- [ ] In-app account deletion tested end-to-end.
- [ ] Location purpose strings match foreground-only driver location.
- [ ] App Review notes include working User and Driver demo accounts/instructions, including MFA.
- [ ] Icons, screenshots, descriptions, support URL, age rating, pricing and availability completed.
- [ ] Review accepted and official listing URL verified.

## Legal and operational sign-off

- [ ] Privacy notice approved by AFCON360's data controller/legal adviser for each launch jurisdiction.
- [ ] Provider inventory, processing countries, legal basis and cross-border safeguards confirmed.
- [ ] Retention periods for identity/KYC, sessions, precise location, trips, Wallet and audit records approved.
- [ ] Support and safety escalation contacts published and tested.
- [ ] Signing-key custody, rollback, app version support and update cadence documented.

The APK path is for internal testers only. Play submission requires a production-signed AAB; iOS requires a separately signed IPA.
