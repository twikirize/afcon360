# Create the AFCON360 internal Android preview signing key (Windows)

This is a one-time setup by the AFCON360 repository owner. The workflow will not publish APKs until the four GitHub Actions secrets below exist.

**Important:** this is a private test-distribution signing key. It must never be committed to Git, attached to an issue/PR, pasted into ChatGPT, or reused as the Google Play production signing key.

## 1. Create a safe local folder

Open Windows PowerShell on a trusted computer that has the JDK `keytool` command available:

```powershell
$signingDir = Join-Path $HOME "afcon360-signing"
New-Item -ItemType Directory -Force -Path $signingDir | Out-Null
$keystorePath = Join-Path $signingDir "afcon360-preview.keystore"
```

Keep this folder outside the AFCON360 source repository.

## 2. Generate the key

Run:

```powershell
keytool -genkeypair -v `
  -keystore $keystorePath `
  -storetype JKS `
  -alias "afcon360-preview" `
  -keyalg RSA `
  -keysize 2048 `
  -validity 10000 `
  -dname "CN=AFCON360 Internal Preview,O=Pamoja,C=UG"
```

Keytool will prompt for the keystore password and then the private-key password. Use a strong, unique password and store it in a password manager. You may press Enter at the private-key password prompt to use the same password as the keystore password; in that case, use the same value for both GitHub secrets.

Validate the keystore and alias:

```powershell
keytool -list -v -keystore $keystorePath -alias "afcon360-preview"
```

## 3. Prepare the Base64 value

This command copies only the Base64 representation to your clipboard:

```powershell
$keystoreBase64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($keystorePath))
Set-Clipboard -Value $keystoreBase64
```

Do not paste the Base64 value into a chat, document, terminal transcript, issue or pull request.

## 4. Add four encrypted GitHub Actions secrets

Open the repository:

1. Go to **Settings → Secrets and variables → Actions**.
2. Choose **New repository secret**.
3. Add these exact names and values:

| Secret name | Value |
|---|---|
| `AFCON360_PREVIEW_KEYSTORE_BASE64` | The Base64 value currently in your clipboard |
| `AFCON360_PREVIEW_KEYSTORE_PASSWORD` | The keystore password from step 2 |
| `AFCON360_PREVIEW_KEY_ALIAS` | `afcon360-preview` |
| `AFCON360_PREVIEW_KEY_PASSWORD` | The private-key password from step 2 |

After saving the secrets, clear the clipboard:

```powershell
Set-Clipboard -Value ""
Remove-Variable keystoreBase64
```

## 5. Back up the key

Keep the `afcon360-preview.keystore` file and passwords in an approved encrypted offline backup/password manager. Do not delete the only copy. Every subsequent preview APK must be signed with this same key to install as an update over an earlier preview build.

The preview signing key is not the production Google Play App Signing key. Production AAB signing and Play App Signing must be configured separately.

## 6. Start the APK build

Once the four secrets are saved:

1. Open the GitHub **Actions** tab.
2. Select **AFCON360 Android preview APKs**.
3. Run the workflow manually on `feat/native-mobile-apps-20261104`, or use **Re-run all jobs** on the latest failed attempt.
4. Confirm both User and Driver jobs pass package, target API, signature and bundled-payload checks.
5. Confirm the combined `mobile-preview` prerelease contains both APKs and `SHA256SUMS.txt`.

The public download/share links are only live after that final publication step succeeds. The APKs are internal Android test builds, not Google Play releases and not iPhone installers.
