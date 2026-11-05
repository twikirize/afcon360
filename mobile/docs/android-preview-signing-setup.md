# Android preview signing — current workflow policy

**Do not follow old instructions to create or add reusable preview-signing secrets for the current PR-capable workflow.**

The workflow at `.github/workflows/mobile-preview-apk.yml`:

- creates a new short-lived CI-only signing key inside the APK-signing step;
- masks the generated password and keeps it within that step;
- uses read-only GitHub token permissions;
- has no stable preview-keystore secret references and no Release-publishing job;
- uploads run-scoped APK and manifest-audit artifacts for validation.

The temporary signing key is not the Google Play production signing key. A later APK signed with a different temporary key cannot update an earlier installation in place. Testers may need to uninstall an earlier preview before installing a new run's artifact; preserve any local test data first.

## Repository secrets

The current workflow does not consume these former repository-level secrets:

- `AFCON360_PREVIEW_KEYSTORE_BASE64`
- `AFCON360_PREVIEW_KEYSTORE_PASSWORD`
- `AFCON360_PREVIEW_KEY_ALIAS`
- `AFCON360_PREVIEW_KEY_PASSWORD`

Do not add them for the current workflow. If these values were added previously, a repository owner should review them under **Settings → Secrets and variables → Actions** and remove any that are no longer needed. I have not changed or inspected repository secret settings.

## Future stable tester distribution

If in-place updates for a stable internal tester group become necessary, create a separate trusted release workflow that pull requests cannot modify. Protect its signing key in a GitHub Environment with required approval and a trusted-branch allowlist, and expose the key only to the minimal signing job. Never reuse preview signing material as the Play App Signing production key.

## Current artifact handling

Download the APK from the successful Android build job's Actions artifact for that run. It is for internal Android validation only, not a permanent public download URL or a Google Play submission package. The iOS CI job creates simulator builds only; it does not create an IPA or submit to App Store Connect.
