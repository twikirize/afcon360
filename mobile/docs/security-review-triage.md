# AFCON360 mobile security and store-readiness triage

Review date: 2026-11-05  
Scope: current AFCON360 User Android preview; Driver and iOS remain outside this phase.

This is a triage record, not a penetration-test certificate or store-approval claim.

## Evidence verified on the current User Android artifact

- Package: `space.pamoja.afcon360.user`.
- Minimum Android API: 24; target API: 36; build uses Android SDK 37.
- APK signature schemes v2 and v3 verified.
- The APK build log checked the packaged manifest and confirmed `android:allowBackup=false`.
- The same checksum-verified artifact installed and launched on emulator API 24, 29, 33 and 36 in [Run #53](https://github.com/twikirize/afcon360/actions/runs/41924848966), and the final workflow-only rerun on 2026-11-04 also passed all four levels.
- User access, refresh and device identifiers are stored through `expo-secure-store`; the inspected User API client enforces HTTPS for non-local API endpoints.
- The inspected User app and mobile-core TypeScript sources contain no direct `AsyncStorage`, custom AES/CBC implementation, MD5/SHA-1 hashing, raw WebView setup or application `console.log/debug/info` statements.
- The PR-capable workflow uses read-only GitHub token permissions, has no stable signing-secret references, and creates a masked ephemeral signing password within the signing step. A fresh APK build is still needed to validate that the masking change appears correctly in build logs.

## Prior MobSF findings — not yet confirmed on the current APK

The available saved item is an earlier analysis note, not the original raw MobSF JSON/PDF. It describes a scan score of 50/100 (Medium) and flags AES-CBC with padding, MD5/SHA-1, logging, WebView/file access, legacy external-storage permissions, `SYSTEM_ALERT_WINDOW`, `libc++_shared.so` stack-canary status, and the AndroidX `ProfileInstallReceiver`. It also records an older certificate subject, `AFCON360 Internal Preview`, whereas the current CI artifact was signed using a short-lived `AFCON360 CI Test` key. The older analysis note is internally inconsistent about the count of High findings. Therefore these are investigation leads, not proof that the same findings exist in the current APK.

### Triage decisions

| Finding | Current decision | Required evidence/action |
|---|---|---|
| Minimum SDK 24 flagged as High | Keep API 24. This is the deliberate device-support baseline, not a Google Play minimum-SDK rejection rule. | Do not raise minSdk based only on a static-scanner score. Restrict a feature only if a concrete OS-specific security issue is demonstrated. |
| `allowBackup` | Fixed in app config and verified in the packaged APK build log. | The new APK manifest audit rechecks the exact artifact. |
| AES-CBC / padding | No app-owned AES/CBC code found in inspected User TypeScript sources. | Use the raw MobSF finding's class, method and library path to locate the owner. If AFCON360-owned cryptography is involved, replace CBC-with-padding with authenticated encryption such as AES-GCM and add compatibility tests. If it is bundled third-party code, upgrade to a vendor-fixed version; do not blindly rewrite platform/library encryption. |
| MD5 / SHA-1 | No app-owned MD5/SHA-1 hashing found in inspected User TypeScript sources. | Trace exact code locations. Do not treat certificate metadata, compatibility checks or a third-party library's internal non-security use as an application password/token weakness. |
| Sensitive logging | No direct console logging found in inspected User TypeScript sources. | Inspect the scanner's exact source paths and release Logcat. Remove app-owned token, password, personal-data and payment logging. |
| WebView/file access | User screens inspected use system-browser handoff for registration/reset and do not directly configure a WebView. Expo/native dependencies may still include WebView code. | Inspect the current packaged manifest and exact MobSF callsites. Restrict file access and navigation only on a WebView that is actually used; do not remove dependencies without tracing their owner. |
| Legacy storage permissions | Not yet verified against the current APK manifest. | Remove broad legacy read/write storage permissions if present and unused. For user-selected uploads, prefer Android Photo Picker / Storage Access Framework rather than broad shared-storage access. |
| `SYSTEM_ALERT_WINDOW` | Not yet verified against the current APK manifest. | Remove it if present and not required by a deliberate, user-visible overlay feature. Do not request overlay access for normal app operation. |
| `ProfileInstallReceiver` | The prior note says it is protected by `android.permission.DUMP`, a privileged/signature permission. | Verify the current receiver's exported and permission attributes. Do not remove the standard AndroidX profile installer receiver solely because MobSF labels it exported. |
| `libc++_shared.so` stack canary / FORTIFY | Appears to be a bundled native runtime/library finding, not yet attributed to AFCON360-owned native code. | Identify the exact binary and supplying dependency. Upgrade to an upstream fixed runtime when available; do not replace the C++ runtime manually or assert exploitability from this heuristic alone. |
| Internal Preview certificate | Not a production signing configuration. | Production Play uses a separate production upload key / Play App Signing and an AAB. The disposable CI signing key is only for internal tests. |

## Store submission blockers

1. **Privacy policy:** `/apps/privacy` is explicitly labelled a working draft. It must be approved, published on an active globally accessible URL, and describe the legal data controller, contact, data categories, purposes, sharing/providers, cross-border processing, retention and deletion.
2. **Data Safety / App Privacy:** complete the Play Data safety and Apple App Privacy declarations from the actual User and Driver binaries, backend flows and every included SDK. Do not guess or declare no collection when identity, sessions, device metadata, trips, location, Wallet and payment state are processed.
3. **Account deletion:** in-app and external web entry points exist, but end-to-end tests are still required. Verify that data not legitimately retained is actually deleted. Document the exact retained record categories, lawful basis and time periods; disabling login/anonymizing identifiers alone must not be treated as a universal substitute for deletion.
4. **Financial features:** complete the Google Play Financial features declaration accurately. Review the Wallet balance and ride-payment capabilities before deciding which feature categories apply.
5. **Reviewer access and app completeness:** provide working review credentials and MFA instructions, ensure the backend is live for review, and make screenshots/listing copy describe only features that are actually accessible in the submitted app.
6. **Production artifacts:** build and inspect a production-signed Android App Bundle with Play App Signing configured. The preview APK is not a store binary.
7. **Device evidence:** emulator install/launch passed, but physical Android testing and live-like sign-in, booking, deletion, Wallet and network-failure journeys are still outstanding.
8. **Apple:** no iOS result is claimed while the iOS job is disabled. Build and TestFlight validation with the currently required Xcode 26 / iOS 26 SDK must be completed before App Store submission.

## Workflow/security operations

- The current PR-capable workflow has `actions: read` and `contents: read`, no stable signing-secret references and no publish job.
- Old repository-level secrets named `AFCON360_PREVIEW_KEYSTORE_BASE64`, `AFCON360_PREVIEW_KEYSTORE_PASSWORD`, `AFCON360_PREVIEW_KEY_ALIAS` and `AFCON360_PREVIEW_KEY_PASSWORD` must be removed if they still exist. The connected GitHub interface cannot verify or delete repository secrets; an owner must inspect Settings → Secrets and variables → Actions.
- The former ephemeral password was unnecessarily visible in an earlier CI log. The current branch creates it inside the signing step, masks it and does not place it in `GITHUB_ENV`. A future fresh build should be inspected to confirm the log is masked.
- Stable internal signing, if needed later, belongs in a separate trusted workflow and protected GitHub Environment with required approval and a release-branch allowlist. Never make a stable or production signing key available to a PR-editable workflow.

## Next evidence gate

The workflow now produces `afcon360-user-apk-manifest-audit`, containing the exact APK's permissions, manifest components, exported/permission attributes, backup/debuggable/cleartext settings and signing details. Review that report, then rerun MobSF on that exact artifact and compare the scanner's component/class paths with the app's source and dependency ownership before deciding which remaining flags require code changes.
