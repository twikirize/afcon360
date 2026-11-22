# AFCON360 Mobile Update & Rebuild Constitution

**Status:** Mandatory engineering policy  
**Current CI enforcement:** AFCON360 User App workflow in .github/workflows/mobile-workspace.yml  
**Applies from:** Adoption on the protected mobile delivery branches

## Preamble

AFCON360 mobile applications must be changed through a test-first delivery process. A new commit, dependency update, configuration change, or feature request is not permission to start an APK build immediately.

The governing rule is:

**Test the update first. Rebuild only when a compatible native binary cannot safely be reused. Never use a successful build as a substitute for tests.**

This constitution applies to the User App and Driver App as independent products. Their package identities, EAS projects, credentials, certificates, runtime fingerprints, OTA channels, update histories, and artifacts must never be mixed. The current automated enforcement described below is implemented for the User App workflow. The Driver App workflow must adopt equivalent gates before being described as compliant.

## Article 1 — Mandatory delivery order

Every mobile update follows this sequence:

**UNDERSTAND → CLASSIFY → MAP → TRACE → TEST → PROVE → DECIDE → BUILD ONLY IF REQUIRED → VERIFY → QUALIFY ON DEVICES → RECORD → RELEASE**

No APK, AAB, native project build, or EAS native build may start before the required pre-build gates for that update have passed.

A failed or skipped required gate is not a pass. A build job must be blocked when a required test job fails, is cancelled, or is skipped.

## Article 2 — Classify the change before selecting a build method

The workflow must classify changed files and identify the strongest change category.

| Change category | Required treatment |
|---|---|
| JavaScript, TypeScript, layout, navigation, copy, and other bundle-compatible changes | Run the applicable source, type, contract, bundle, and integration tests. Use OTA only with a runtime-compatible installed binary. Do not rebuild the native APK just because the source commit changed. |
| Backend/API changes | Test the mobile-to-API contract against an isolated backend environment. Backend deployment is a separate release decision. A backend-only change does not justify a mobile APK rebuild. |
| Native dependency, native plugin, app config, Android/iOS project, Gradle, native permission, SDK, or other native-runtime change | Run all pre-build tests first, then calculate the Expo native fingerprint. Reuse a verified binary only when its fingerprint and build recipe are compatible. Otherwise perform one candidate native build. |
| CI, verifier, or test-harness-only changes | Run the relevant checks and integration tests. Do not rebuild a mobile binary unless the native build recipe itself changed or a deliberate baseline build is required. |
| Mixed changes | Apply the strictest applicable category. All required checks must pass before any candidate build. |

File classification is an initial signal, not the final rebuild decision. The native fingerprint and verified build metadata decide whether an existing binary can be reused.

## Article 3 — PRE-BUILD TEST GATE

The following checks must complete successfully before a native build begins.

### 3.1 Source, dependency, and configuration checks

- Install the workspace dependencies and validate the User App package graph.
- Run the approved navigation and native account-deletion checks.
- Parse the Windows development helper scripts that are part of the local testing path.
- Verify the offline-storage, authentication, session, server-selection, and update-channel contracts.
- Verify both development and production Expo configuration. A local development API address must not leak into a production build, and production must not resolve to a loopback or plain-HTTP API.
- Confirm that the User App and Driver App identities and update channels remain separate.

An Expo dependency advisory must be recorded. It must not be silently converted into a dependency or lockfile update merely to make the warning disappear. The blocking TypeScript, bundle, configuration, and integration gates must still pass.

### 3.2 Application compilation checks

- Run strict TypeScript validation.
- Export the Android JavaScript bundle.
- Export the iOS JavaScript bundle.
- Run the executable mobile architecture and delivery-contract verifier.

These checks must finish before any candidate APK is built.

### 3.3 Backend and session integration checks

When a mobile runtime, API contract, or relevant test-harness change is detected, run the backend pre-build integration job against disposable PostgreSQL and Redis services. The test account and test data must be synthetic.

The current User App pre-build suite verifies the native login/token path, Redis and PostgreSQL session linkage, protected identity and wallet reads, accommodation and event reads, and exact device/server session revocation after logout. It also verifies that the revoked token is no longer accepted. The job must upload its evidence.

These are test-environment operations only. They must not create real bookings, move money, send real messages, or write to production databases or Redis.

## Article 4 — Fingerprint and binary reuse decision

After all applicable pre-build gates pass:

1. Calculate the current Expo native fingerprint.
2. Calculate the relevant build-profile and build-recipe identity.
3. Search for a previously verified APK that matches those values.
4. Verify its recorded package identity and SHA-256 before reuse.

The decision is:

- **Exact compatible binary found:** reuse it. Do not start EAS or Gradle merely because JavaScript or the Git commit changed.
- **No compatible binary exists:** one baseline/candidate build is permitted after all pre-build gates pass.
- **Native fingerprint or required build recipe changed:** one new candidate build is permitted after all pre-build gates pass.
- **Test-harness-only change:** no native rebuild. Re-run the tests against the compatible cached binary where a device journey is required.
- **Explicit force-rebuild request:** it may bypass binary reuse, but it must never bypass classification, source checks, TypeScript, bundle exports, backend integration tests, or configuration gates.

The authenticated-journey APK cache is keyed by native fingerprint and build recipe, not by the JavaScript source commit. The current JavaScript bundle is delivered to that test binary through the isolated E2E OTA channel. This prevents needless native rebuilds while ensuring the device journey tests the current JavaScript update.

A cache entry is not trusted merely because it exists. Its hash, package, native fingerprint, and required build metadata must be verified before reuse.

## Article 5 — One candidate build

For a given native fingerprint and build recipe, the workflow must produce at most one new candidate binary and reuse that verified result for subsequent compatible checks.

Do not create a temporary APK, discard it, and then build a second APK for the same candidate. Do not run parallel native builds for the same app identity and purpose unless a separate platform or signing target genuinely requires it.

If the candidate build fails, stop. Diagnose the failing step and correct the source or build configuration. Do not repeatedly rebuild without a new, evidence-based reason.

## Article 6 — POST-BUILD BINARY VERIFICATION

A successful EAS or Gradle exit code is not sufficient.

The candidate APK must be checked for:

- Correct application package ID and app identity.
- Expected app version and a valid version code.
- Required Android minimum and target SDK levels.
- A valid Android signing certificate and recorded certificate SHA-256.
- APK SHA-256 and file integrity.
- Expected API configuration, server-selection capability, update channel, and native fingerprint.
- Build metadata tying the artifact to its source commit and build recipe.

Any mismatch blocks the candidate. Never rename a Driver App binary as a User App binary or vice versa.

## Article 7 — Device qualification before tester approval

A CI-uploaded APK is a **candidate artifact**, not automatic approval for distribution.

Before an APK is declared ready for pilot testers, the exact candidate binary must be installed and exercised on Android devices. The qualification record must cover:

- Installation, launch, upgrade/reinstall behaviour, and app identity.
- Connection to the intended laptop development server and API.
- Server selection and switching between supported local/LAN/USB modes.
- Login, session restoration, logout, and protected API access.
- Primary navigation and the key journeys changed by the update.
- Logs and evidence for any failure, including device model, Android version, APK SHA-256, and test outcome.

The planned pilot is three to five Android phones. A successful backend test, JavaScript bundle export, or test of a different APK does not replace testing the exact candidate Metro development-client APK.

Until the exact Metro APK has passed device qualification, its CI artifact remains a candidate for controlled internal evaluation. It must not be described as a fully qualified tester release.

## Article 8 — OTA update governance

OTA is allowed only when the installed binary's runtime fingerprint is compatible with the update.

- Publish test updates to isolated development or E2E channels first.
- Keep the Metro development-client channel separate from normal preview and production channels.
- Keep User and Driver OTA channels separate.
- Do not use an OTA update to deliver a native dependency, permission, plugin, manifest, or native-runtime change.
- A successful OTA publish is not proof that the app works. The bundle and the relevant API/device journeys must be tested.
- Production OTA publication requires an explicit release decision and must never happen as an accidental side effect of a development workflow.

## Article 9 — User App and Driver App independence

The User App and Driver App are separate installable products. Each must retain its own:

- Android package ID and application identity.
- iOS bundle ID.
- EAS project linkage.
- Signing credentials and certificate history.
- Native fingerprint and build cache.
- OTA project, channel, and runtime compatibility.
- Build artifact names and evidence.

A change or test in one app must not invalidate, overwrite, publish to, or distribute the other app's artifacts.

## Article 10 — Failure handling and test integrity

When a gate fails:

1. Stop all dependent builds and publication jobs.
2. Identify the actual failing test, command, or infrastructure dependency.
3. Separate source defects from environment/setup failures.
4. Preserve logs and test evidence.
5. Make the smallest justified correction.
6. Re-run the failed gate and all downstream gates that the correction could affect.

Do not weaken assertions, skip failed tests, fabricate evidence, or alter production data to obtain a green workflow. An infrastructure failure must be recorded as inconclusive, not as a passing test.

## Article 11 — Required evidence record

Every candidate or release record must include:

- Source branch and full commit SHA.
- Changed-file classification and reason for build/no-build decision.
- TypeScript, contract, bundle-export, and backend integration outcomes.
- Native fingerprint, profile/build-recipe identity, and cache hit/miss decision.
- Whether a new binary was built or an existing verified binary was reused.
- APK package, version, signing certificate SHA-256, artifact SHA-256, and download artifact identifier.
- OTA project/channel/branch and update identifier, when applicable.
- Device qualification results for the exact candidate binary.
- Explicit release authority and release scope.

Keep evidence attached to the CI run or the repository's release record. A green badge without these details is not a complete engineering record.

## Article 12 — Production and data protection

Development and CI workflows must use disposable databases, synthetic users, and isolated Redis namespaces. No production database migration, write, reset, booking, payment, wallet movement, refund, or live OTA publication may be performed without the separate required approval.

The development Metro APK must remain pointed at the intended local development configuration by default. A developer must intentionally select a different permitted server. The ordinary live Pamoja app must not depend on Metro.

## Article 13 — Current CI enforcement and known boundary

The User App workflow enforces the pre-build sequence through:

- The mobile source/type/configuration and Android/iOS bundle checks.
- The disposable PostgreSQL/Redis backend pre-build integration job.
- Build-job dependencies that require successful pre-build evidence.
- Fingerprint- and recipe-based APK cache validation.
- Isolated E2E and Metro development OTA channels.
- An executable verifier that checks these workflow rules for regressions.

The exact Metro development-client APK is currently checked for signing, package identity, SDK levels, API/channel configuration, and SHA-256 in CI. The current Metro job does not yet automatically perform the full three-to-five-phone device qualification described in Article 7. Therefore its artifact remains a candidate until that device evidence is recorded. The older authenticated Android journey is a separate test path and must not be represented as proof that the exact Metro APK passed that device test.

The Driver App pipeline must be reviewed and brought under equivalent controls before this constitution is claimed to be fully automated for both apps.

## Article 14 — Authority

No workflow, agent, developer, or automated tool may bypass the mandatory pre-build gates by default. A force-rebuild option may request a new binary, but it does not waive tests or release controls. Production release and tester-distribution approval remain explicit decisions.

---

## Non-negotiable rule

**No build first and discover missing pieces later. Test the update first, prove the evidence, reuse a compatible binary whenever possible, and rebuild only when the native fingerprint or verified build recipe requires it.**
