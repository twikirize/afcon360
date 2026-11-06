# Internal Android preview signing — current policy

The former instructions for generating a reusable preview keystore and storing `AFCON360_PREVIEW_KEYSTORE_*` values as repository Actions secrets are retired for the current workflow.

The PR-capable CI workflow creates a disposable signing key inside the APK-signing step, masks its password, uses read-only GitHub token permissions and uploads a run-scoped Actions artifact. It has no reusable signing-secret references and does not publish Releases.

**Do not add stable preview credentials as repository-level Actions secrets for this workflow.** If the old four secrets already exist, the repository owner should review and remove any that are no longer needed in **Settings → Secrets and variables → Actions**. This work has not changed repository secret settings.

Every run may have a different signature. Android may therefore require uninstalling an earlier temporary-key test build before installing a new artifact. Preserve any local test data first. The APK is not a production update.

If AFCON360 later needs in-place updates for a stable tester group, create a separate trusted release workflow that pull requests cannot modify. Store its key only in a protected GitHub Environment with required approval and a strict trusted-branch allowlist. Keep the key out of all PR-capable jobs.

## Store signing is separate

- Google Play receives a production-signed Android App Bundle (`.aab`) with Play App Signing configured.
- Internal preview APKs are only for direct Android testing.
- Apple receives a separately signed iOS archive/IPA.
- Never reuse preview credentials for Google Play or Apple production distribution.

See [the current platform compatibility policy](platform-compatibility.md) and [the store submission checklist](store-submission-checklist.md).
