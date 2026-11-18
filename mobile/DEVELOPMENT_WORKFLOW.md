# AFCON360 Native App Change and Release Workflow

This document describes how to change AFCON360 User and Driver safely and efficiently.

> The native source is currently staged in this repository under `mobile/` while the separate `afcon360-apps` repository is prepared. Keep app-only changes on the native app PR/branch. Do not put native app source into website `main`.

## 1. Start with the requested behavior

Describe what should change, where it appears, and what should happen instead. A screenshot is useful for a visual problem, but explain the expected behavior too.

Examples:

- "On User > Wallet, rename 'Available balance' to 'Wallet balance'."
- "Remove the extra website deletion link from Driver > Account. Keep the native deletion screen."
- "When I tap Forgot password, keep me in the app and let me reset using an email code."
- "On Driver > Trips, show the pickup address above the destination."

Before editing, identify whether the request belongs to:

| Change type | Source area | Typical impact |
|---|---|---|
| User screen, text, layout or navigation | `mobile/apps/user/app/` | User app |
| Driver screen, text, layout or navigation | `mobile/apps/driver/app/` | Driver app |
| Shared button, form, screen shell or theme | `mobile/packages/ui/` | Both apps |
| API calls, authentication or secure token handling | `mobile/packages/core/` | Both apps and server contract |
| App ID, URL scheme, permissions, plugins or native config | Each app's `app.config.ts` | Native rebuild and compatibility checks |
| EAS build profiles | Each app's `eas.json` | Build/release behavior |
| Flask route, model, database, email or business rule | Website repository `afcon360` | Server change and backend tests |

Never edit a generated APK to change a screen. APKs are build outputs; the source code is authoritative.

## 2. Check dependencies before changing behavior

- Read `AGENTS.md`, `docs/backend-contracts.md`, `docs/api-inventory.md` and `docs/release-gates.md`.
- For an API operation, confirm the endpoint, request body, response shape, authorization and error states in the server contract.
- Do not invent endpoints, fields, balances, fares, trip states or payment behavior.
- Keep financial authority on the server. The app must not calculate or decide wallet balances, payment success, fares, driver eligibility or booking state.
- If the server contract is missing or wrong, open a separate server change. Keep the app code compatible with the reviewed server contract.

## 3. Make the smallest complete source change

- Prefer the smallest screen/component/service that owns the behavior.
- If a shared package changes, check both User and Driver callers.
- Keep loading, success, empty, validation and failure states. Do not make a button appear functional when the server operation is not implemented.
- Keep credentials in SecureStore. Never put secrets in `EXPO_PUBLIC_*`, logs, URLs or ordinary local storage.
- Use explicit labels when an action intentionally opens the official website.
- Keep password reset and account deletion in native flows. Do not add browser shortcuts for these functions.
- Do not introduce background driver tracking. Location remains permission-gated and foreground/driver-initiated unless a separately reviewed feature changes that policy.

## 4. Run the fast checks before requesting a platform build

From the `mobile/` directory:

```bash
pnpm install
pnpm navigation:check
pnpm --filter @afcon360/user-app exec expo install --check
pnpm --filter @afcon360/driver-app exec expo install --check
pnpm typecheck
```

Then export both app bundles for the platforms affected by the change:

```bash
pnpm --filter @afcon360/user-app exec expo export --platform android --output-dir /tmp/afcon360-user-android
pnpm --filter @afcon360/user-app exec expo export --platform ios --output-dir /tmp/afcon360-user-ios
pnpm --filter @afcon360/driver-app exec expo export --platform android --output-dir /tmp/afcon360-driver-android
pnpm --filter @afcon360/driver-app exec expo export --platform ios --output-dir /tmp/afcon360-driver-ios
```

The repository CI runs these workspace and navigation checks. Do not hide TypeScript or dependency failures by weakening checks or adding broad exclusions.

## 5. Decide whether a new binary is required

| Change | New Android/iOS build? |
|---|---|
| Screen text, layout, React Native component, navigation, JavaScript logic or bundled image/content | **No**, after an OTA-enabled binary is installed; publish an EAS Update |
| Shared UI or API-client JavaScript behavior | **No**, after an OTA-enabled binary is installed; publish an EAS Update |
| Flask endpoint/business-rule change only | No app rebuild if the app binary and client contract do not change |
| Native permission, native library/module, plugin, application ID, URL scheme, Android/iOS manifest, native build setting or SDK upgrade | **Yes**; build and install a new binary |
| Website template/CSS change only | No app rebuild; those website assets are not bundled into the native APK/IPA |

The User app is being configured for Expo Updates with separate `preview` and `production` channels. Ordinary JavaScript, screen and bundled-asset changes can be published from GitHub to the User preview channel after the CI checks pass. The app checks for compatible updates when it starts and applies a downloaded update on a subsequent launch/reload; it does not rebuild or reinstall the APK for those changes.

The existing preview APK built before Expo Updates was added cannot receive OTA updates. One new OTA-enabled APK must be built and installed once. After that, ordinary compatible JavaScript/UI changes do not require another APK build.

The runtime policy is `appVersion`. Any change to native code or native configuration must also increment the app version and produce a new binary. This keeps OTA updates from being sent to binaries with a different native runtime. Never publish JavaScript that calls a native module not present in the installed binary.

## 5A. User OTA publishing and safeguards

The User GitHub workflow publishes to the **preview** EAS Update channel after its dependency, TypeScript, Android bundle and iOS bundle checks pass. It runs on User-app changes pushed to the User feature branch. It does not publish to production. Android device and authenticated-journey checks remain separate release evidence; emulator infrastructure failures must be diagnosed rather than treated as app compatibility failures.

To activate publishing, configure these GitHub Actions settings for the repository:

- Repository variable `AFCON360_USER_EAS_PROJECT_ID`: the UUID of the dedicated **User** EAS project. Do not reuse a Driver project ID.
- Repository secret `EXPO_TOKEN`: an Expo access token permitted to publish updates to that User project.

The project ID is public configuration; the token is a secret. Do not put the token in source code or any `EXPO_PUBLIC_*` variable.

After setting the project ID, run **Actions → Build OTA-enabled AFCON360 User preview APK → Run workflow** on the User feature branch. Install the resulting `afcon360-user-ota-enabled-preview-apk` artifact once. The earlier `AFCON360-User-WiFi-Preview-3b03c06.apk` was built without the Expo Updates native client and cannot receive OTA updates. Once the new binary is installed and `EXPO_TOKEN` is configured, compatible User UI/JavaScript changes pushed to this branch are published automatically to the preview channel. The app checks at startup and applies a downloaded update on a later launch/reload.

Production updates are not published automatically from the User feature branch; they require a separately approved production release. Native code, permissions, SDK or plugin changes still require a new binary and app-version/runtime change.

## 6. Review through a pull request

1. Work on a focused feature/fix branch, not app `main`.
2. Keep the change app-only. Flask, templates, migrations, Docker and server tests belong in the website repository.
3. Run the fast checks above.
4. Open/update the app pull request and summarize the behavior changed, files touched, API dependencies and test evidence.
5. Review the actual diff. Check that no secrets, generated native folders, debug settings or unrelated files were added.
6. Merge only after the required CI and human/device checks pass.

## 7. Understand the preview builds

The PR-capable GitHub workflow builds both User and Driver Android preview APKs and runs compatibility checks. It also builds and launches both iOS simulator apps.

A green workflow must be tied to the exact source commit being reviewed. Check the run's commit SHA, job conclusions and artifact list before distributing anything.

Current preview signing is deliberately disposable:

- A new short-lived signing key is generated for each CI run.
- APKs are uploaded as run-scoped GitHub Actions artifacts.
- They are not permanent download URLs, production-signed APKs or Play Store packages.
- An APK from a later run may not update an earlier preview installation because the signing key differs. Uninstall only the old preview app if Android reports a signature mismatch; preserve test data first.
- CI iOS outputs are simulator builds, not signed TestFlight/App Store IPAs.

Install and test the preview on real devices after emulator/simulator checks. Validate login, password reset, navigation, permissions, network loss/recovery, and the specific changed journey.

## 8. Production release is a separate gate

A preview APK is not a production update.

- Android production requires a Play App Signing-compatible production release, normally an AAB.
- iOS production requires a correctly signed archive/IPA and a TestFlight/App Store review path.
- Confirm the production app IDs and signing identities are unchanged.
- Confirm API/server dependencies are merged, deployed and smoke-tested before enabling the app flow.
- Complete physical-device acceptance, privacy/legal disclosures, store metadata and operational support checks.
- Record the exact source commit, build number, artifact checksum and release approval.

Never perform a production database migration, deploy/restart server containers, change signing credentials or submit to a store as part of an ordinary UI edit. Each needs its own reviewed release step and authorization.

## 9. Efficient change requests

A good request can be one sentence:

**"In [User/Driver] > [screen], change [current behavior] to [expected behavior]. Keep [important rule] unchanged."**

The implementation should then follow:

**Understand → locate the owner → inspect dependencies → minimal source change → fast checks → PR review → preview build → device test → approved release.**

This avoids rebuilding for unrelated website-only changes, avoids compiling stale source, and prevents app behavior from drifting away from server-owned business rules.
