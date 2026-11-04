# Internal Android preview signing setup (Windows PowerShell)

The APK workflow requires one stable internal signing key so a tester can install a new preview APK over the previous version. This key is only for internal preview builds. It is not the Google Play production signing key.

**Keep the keystore and passwords private. Do not commit the keystore, upload it to the public repository, or send its contents/passwords in chat.** Keep an encrypted backup: losing this key prevents in-place updates to APKs signed with it.

## 1. Create a stable keystore on your Windows machine

Open PowerShell on a trusted machine with Java 17 or newer available. Run:

\`\`\`powershell
$signingDirectory = Join-Path $HOME "afcon360-preview-signing"
New-Item -ItemType Directory -Force -Path $signingDirectory | Out-Null
Set-Location $signingDirectory

# Generate a random 256-bit password without printing it in the command.
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$storePass = [Convert]::ToBase64String($bytes).TrimEnd('=')

# Use the same strong password for the keystore and its key entry.
$env:AFCON360_PREVIEW_STORE_PASSWORD = $storePass
$env:AFCON360_PREVIEW_KEY_PASSWORD = $storePass

keytool -genkeypair -v -keystore .\afcon360-preview.keystore -storetype PKCS12 -storepass:env AFCON360_PREVIEW_STORE_PASSWORD -keypass:env AFCON360_PREVIEW_KEY_PASSWORD -alias afcon360-preview -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=AFCON360 Preview,O=Pamoja,C=UG"

# Confirm that the keystore and alias can be read.
keytool -list -keystore .\afcon360-preview.keystore -storetype PKCS12 -storepass:env AFCON360_PREVIEW_STORE_PASSWORD -alias afcon360-preview
\`\`\`

The commands do not print the private key or password. Keep this PowerShell window open until all four GitHub secrets have been added.

## 2. Add the four encrypted GitHub Actions secrets

Open the AFCON360 repository on GitHub:

**Settings → Secrets and variables → Actions → New repository secret**

Create these four secrets one at a time:

| Secret name | Secret value |
|---|---|
| AFCON360_PREVIEW_KEYSTORE_BASE64 | Base64-encoded keystore from the PowerShell commands below |
| AFCON360_PREVIEW_KEYSTORE_PASSWORD | The generated password in $storePass |
| AFCON360_PREVIEW_KEY_ALIAS | afcon360-preview |
| AFCON360_PREVIEW_KEY_PASSWORD | The same generated password in $storePass |

To copy the Base64 keystore value, run:

\`\`\`powershell
$keystorePath = (Resolve-Path .\afcon360-preview.keystore).Path
$keystoreBase64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($keystorePath))
Set-Clipboard -Value $keystoreBase64
\`\`\`

Paste the clipboard value into the GitHub secret named AFCON360_PREVIEW_KEYSTORE_BASE64.

To copy the password for each of the two password secrets, run:

\`\`\`powershell
Set-Clipboard -Value $storePass
\`\`\`

Paste into AFCON360_PREVIEW_KEYSTORE_PASSWORD and AFCON360_PREVIEW_KEY_PASSWORD. For AFCON360_PREVIEW_KEY_ALIAS, enter the literal text afcon360-preview.

Do not add these values as ordinary repository variables. They must be **Actions secrets**. The workflow intentionally stops if any one is missing.

## 3. Run the preview build

After all four secrets are saved:

1. Open the repository's **Actions** tab.
2. Select **AFCON360 Android preview APKs**.
3. Select **Run workflow** and choose branch **feat/native-mobile-apps-20261104**.

The workflow builds User and Driver in parallel. It checks the application IDs, target API 36 or higher, APK signatures and packaged DEX content. It then publishes both APKs and SHA-256 checksums only if the build still matches the latest feature-branch commit.

The download/share buttons use the stable GitHub Release asset URLs. They become live only after that release has both APK files.

## 4. What this key is not

- It is not the Google Play App Signing key.
- It is not an Apple signing certificate or provisioning profile.
- Do not reuse a production keystore for preview builds.
- Do not rotate or replace this preview key after distributing APKs unless testers are prepared to uninstall the old preview before installing the newly signed one.
