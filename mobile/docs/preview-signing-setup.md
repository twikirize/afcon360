# Internal Android preview signing — current policy

The former instructions for generating a reusable preview keystore and storing four `AFCON360_PREVIEW_KEYSTORE_*` values as repository Actions secrets are **retired**.

The current PR-capable workflow creates a disposable CI signing key within the APK-signing step, masks its password, uses read-only GitHub token permissions, and uploads an Actions artifact. It has no reusable signing-secret references and does not publish releases.

**Do not add stable preview signing credentials as repository-level Actions secrets for this workflow.** If the old four secrets are already present, remove them from **Settings → Secrets and variables → Actions**. The current workflow must never receive a Play production signing key.

A one-time CI key means a later artifact may have a different certificate. Android may therefore require the tester to uninstall a previous temporary-key build before installing the next one. Treat the test APK as disposable; it is not the store build.

If AFCON360 later needs in-place updates for a stable internal tester group, create a separate trusted release workflow that PRs cannot modify. Store its key only in a protected GitHub Environment with required approval and a strict trusted-branch allowlist. Expose the secret only to the minimal signing job.

## Store signing is separate

- Google Play receives a production-signed Android App Bundle (`.aab`) with Play App Signing configured.
- An internal Android preview APK is only for direct testing.
- Apple receives a separately signed iOS archive/IPA.
- Never reuse preview credentials for Google Play or Apple production distribution.

See [the Android preview workflow](../.github/workflows/mobile-preview-apk.yml) and [the store submission checklist](store-submission-checklist.md) for current release gates.