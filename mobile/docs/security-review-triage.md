> **Historical security triage — review before relying on individual findings.** This note originated from a User-only review dated 5 November 2026. It is retained because it records security and account-deletion investigation leads that are not covered by the platform build checks. Some platform statements below have since been superseded: on 6 November 2026, both User and Driver passed Android API 24/29/33/36 install-and-launch checks, both Android manifest audits passed, and both iOS simulator build/install/launch checks passed in [workflow run 42094917580](https://github.com/twikirize/afcon360/actions/runs/42094917580). That run does **not** prove that every security finding below is fixed, that account deletion erases all user-linked data, or that a signed iOS IPA exists. Revalidate every finding against the current APKs and backend before closing it.

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
| Legacy storage permissions | Confirmed in the exact APK manifest: READ/WRITE_EXTERNAL_STORAGE were declared with maxSdkVersion 32. The current User app has no file/media upload or shared-storage UI/code. | Fixed in both User and Driver Expo configs using `android.blockedPermissions`. A fresh APK build and manifest audit are running to prove the permissions are absent. Future user-selected uploads must use Android Photo Picker / Storage Access Framework and scoped content URIs rather than broad shared-storage access. |
| `SYSTEM_ALERT_WINDOW` | Confirmed in the exact APK manifest. No User or Driver product feature requires drawing over other apps. | Fixed in both User and Driver Expo configs using `android.blockedPermissions`. A fresh APK build and manifest audit are running to prove it is absent. |
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
8. **Apple:** both User and Driver iOS simulator build/install/launch checks now pass, including the iOS 16.4 deployment-minimum validation. This is simulator evidence only; physical iPhone testing, a production-signed archive/IPA and TestFlight validation remain outstanding.

## Account deletion — confirmed cross-module gap (high priority)

The current shared deletion service performs strong identity/session actions: it reauthenticates by password and enrolled TOTP/backup code, blocks protected accounts and certain active transport obligations, revokes device/server sessions, tombstones the User sign-in record, anonymizes the general UserProfile, retires driver location/contact data, invalidates MFA/recovery/PIN material and revokes user-owned API keys.

That is **not yet a complete account-data deletion implementation**. Source inspection found additional user-linked records and snapshots that the service does not scrub or classify:

| Domain | Confirmed fields / relationship | Risk and required decision |
|---|---|---|
| Events | `EventRegistration` retains `full_name`, `email`, `phone`, `nationality`, `id_number` even when `user_id` is set null; `EventGuest` retains name/email/phone; `Waitlist` retains email/phone. | Map which fields are needed for ticket validity, safety, fraud or statutory evidence. Erase/anonymize non-required PII; time-limit and restrict access to legally required identity evidence. Preserve ticket/payment integrity without displaying deleted-person details to ordinary event users. |
| Accommodation | `AccommodationBooking` may hold `guest_name/email/phone`, `owner_email`, `primary_guest_name/email/phone`, `booked_by_name_snapshot/email_snapshot`, special requests, guest instructions and context metadata, as well as multiple User foreign keys. | Check upcoming/active stays and guest rosters before allowing closure. Preserve only booking/payment/dispute evidence that has an approved legal basis; scrub non-required contact snapshots, special requests and personal metadata after obligations end. |
| Transport | `Booking` keeps pickup/dropoff addresses, contact names/phones, coordinates and metadata; `TransportPassenger` keeps name/email/phone snapshots even if its `user_id` is cleared. | Resolve active/upcoming trips and safety/dispute obligations. Retain only minimum necessary ride/settlement evidence; remove or pseudonymize passenger/contact snapshots and location precision when no longer needed. |
| Wallet / payment identity | `PaymentIdentityModel` keeps active verified phone/email/AFCON360-ID addressability. The recipient resolver selects `is_active=True` identities and accepts an account only when its status is ACTIVE. User soft deletion does not execute database FK cascade. `AccountModel` has independent `status` and `is_frozen` state. | Do not leave deleted users discoverable as payment recipients. Deactivate their active payment identities and close/freeze the associated user wallet under an approved balance, payout, refund and dispute process. Never zero/delete ledger entries or silently forfeit a positive balance. |
| Financial/audit/KYC | Account and ledger ownership, wallet transactions, KYC evidence and audit references are intentionally durable. | Define a record-by-record statutory/contractual retention matrix: data item, lawful purpose, jurisdiction, retention start/event, exact period, access roles, deletion/anonymization action and expiry job. “May be retained where required” is not an adequate published retention schedule. |

### Required safe remediation sequence

1. Build a complete user-data inventory across Identity, Profile, Transport, Accommodation, Events, Wallet, payment providers, uploads/object storage, notifications, analytics and audit sinks. Include JSON/metadata fields and processor copies, not just FK relationships.
2. Define which outstanding service obligations must be completed, cancelled, transferred or refunded before account closure. Extend the current active-transport checks to active/upcoming accommodation and event obligations where applicable. Do not trap users indefinitely; provide a documented support/escalation path.
3. Revoke login/device/API credentials and deactivate reusable payment identities. For wallets, use the wallet's controlled freeze/closure process and provide a lawful path for remaining funds, pending payouts, reversals and chargebacks. Keep the ledger immutable.
4. Apply domain-owned anonymization/deletion functions in one coordinated transaction or an idempotent deletion job with per-domain completion state, retry, audit and failure handling. Avoid ad-hoc cross-module bulk updates in Identity.
5. Keep legally required ticket, contract, KYC, AML, accounting and dispute records only where there is a documented legal basis and retention period. Restrict access and remove direct identifiers that are not needed for the retained purpose.
6. Add integration tests per domain: before/after queries for each PII category, active obligation rejection, positive wallet balance, unsettled payment, retry/idempotency, payment-recipient lookup after deletion, and retained-evidence authorization.
7. Publish exact retention categories/periods and external deletion-request handling only after the data controller/legal adviser approves them. Then verify both the in-app and public web deletion paths against the same service.

**Do not declare account deletion store-ready until these tests and the retention schedule are complete.** The current UI and shared service exist, but they establish only identity tombstoning/profile anonymization plus session/credential revocation—not erasure of every personal record held by AFCON360 or its processors.

## Workflow/security operations

- The current PR-capable workflow has `actions: read` and `contents: read`, no stable signing-secret references and no publish job.
- Old repository-level secrets named `AFCON360_PREVIEW_KEYSTORE_BASE64`, `AFCON360_PREVIEW_KEYSTORE_PASSWORD`, `AFCON360_PREVIEW_KEY_ALIAS` and `AFCON360_PREVIEW_KEY_PASSWORD` must be removed if they still exist. The connected GitHub interface cannot verify or delete repository secrets; an owner must inspect Settings → Secrets and variables → Actions.
- The former ephemeral password was unnecessarily visible in an earlier CI log. The current branch creates it inside the signing step, masks it and does not place it in `GITHUB_ENV`. A future fresh build should be inspected to confirm the log is masked.
- Stable internal signing, if needed later, belongs in a separate trusted workflow and protected GitHub Environment with required approval and a release-branch allowlist. Never make a stable or production signing key available to a PR-editable workflow.

## Next evidence gate

The latest workflow produces User and Driver APK manifest-audit artifacts, and both audit jobs passed in run 42094917580. The audit artifacts must still be inspected before claiming the state of any individual permission/component or declaring a prior MobSF finding resolved. Rerun MobSF on the latest exact artifacts and compare scanner class paths with current source/dependency ownership before deciding which remaining flags require code changes.
