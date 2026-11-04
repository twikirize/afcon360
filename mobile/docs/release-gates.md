# Mobile release gates

A release advances only when evidence for its gate is recorded.

## Gate 0 — repository and local build

- [ ] SDK 58 workspace installs with pnpm.
- [ ] Both apps pass expo-doctor and TypeScript checks.
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
