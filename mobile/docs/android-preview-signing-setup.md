# Android preview signing — current workflow

**This document supersedes the old stable-keystore setup instructions. Do not create or add the old repository-level preview-signing secrets for the current workflow.**

The PR-capable workflow at `.github/workflows/mobile-preview-apk.yml` currently:

- creates a fresh, short-lived CI-only signing key inside the APK-signing step;
- masks the generated password and does not place it in `GITHUB_ENV`;
- has read-only GitHub token permissions;
- contains no stable preview-keystore secret references and no APK publishing job;
- uploads the tested APK as a GitHub Actions artifact.

The key is disposable and is **not** the Google Play production signing key. A later APK signed with a different temporary key cannot update an already-installed copy in place. A tester may need to uninstall the old test copy before installing a later artifact; preserve any data needed first.

## Protect GitHub signing secrets

If any of these old repository-level Actions secrets exist, remove them from **Repository → Settings → Secrets and variables → Actions**:

- `AFCON360_PREVIEW_KEYSTORE_BASE64`
- `AFCON360_PREVIEW_KEYSTORE_PASSWORD`
- `AFCON360_PREVIEW_KEY_ALIAS`
- `AFCON360_PREVIEW_KEY_PASSWORD`

The current PR workflow must not receive stable preview or production signing keys. A same-repository pull request can propose edits to a PR-triggered workflow, so merely adding a conditional around a secret reference in that workflow is not a durable protection.

## When stable internal preview updates are needed

Design a separate trusted release workflow before reintroducing a reusable test key. Keep its workflow definition outside PR-editable paths, use a protected GitHub Environment with required approval and a deployment-branch allowlist, and scope the key to the smallest trusted signing job. Never use a preview key as the Play App Signing production key.

## Downloading the current test build

Use the successful User Android artifact from the Actions run linked in the release handover. Download the ZIP, extract `user-preview.apk`, and install it on an Android device. The artifact is for internal testing only; it is not a Play Store submission package.