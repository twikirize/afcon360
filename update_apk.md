# Pamoja User App - Update Guide (Metro and EAS)

A plain-English guide for developing, testing, and updating the Pamoja User app on Android.

- Last updated: 26 November 2026
- Mobile project folder: `C:\Users\OBED\Desktop\afcon360-user-dev`
- Backend project folder: `C:\Users\OBED\Desktop\afcon360_app`

---

## 0. The 30-second summary

There are two different ways to get new code onto the phone:

| Method | What it does | Speed | Needs laptop? | Survives app restart? |
|---|---|---|---|---|
| **Metro** | Sends code live from your laptop to the Developer app | About 1 second | Yes | No |
| **EAS Update** | Downloads a new JavaScript bundle from the cloud to the Preview app | A few minutes | No | Yes |

There are also two different apps on the phone:

| App | Package ID | Use it for |
|---|---|---|
| **AFCON360 Developer** | `space.pamoja.afcon360.user.preview.dev` | Live coding with Metro |
| **AFCON360 Preview** | `space.pamoja.afcon360.user.preview` | Testing, demos, offline use, EAS updates |

**You do not need to rebuild the APK for normal screen, text, style, navigation, or logic changes.** A new APK is only needed when native code or native configuration changes.

---

## 1. Which app am I opening?

Check the name under the icon:

- **AFCON360 Developer** = the Metro app. It can connect to your laptop. It has the "Metro Bundler (Fast Refresh)" option in Connection settings.
- **AFCON360 Preview** = the standalone app. It does **not** connect to Metro. Its Connection settings only chooses the backend API server.

This is the most common source of confusion:

- If you close Metro and the old code comes back, you are probably in the **Developer** app. That is expected.
- If you want code to stay on the phone without the laptop, use the **Preview** app and an EAS Update.

---

## 2. Where the phone gets its code

### 2.1 The Preview app

The Preview app has two code sources:

1. **Downloaded EAS Update** - the newest update that was downloaded and successfully applied.
2. **Built-in APK bundle** - the code frozen inside the APK when it was built. This is the fallback.

On launch, the Preview app:

1. Opens with the current code.
2. Checks EAS for a newer compatible update.
3. Downloads it in the background.
4. Applies it on the **next** launch.

After that second launch, the downloaded update is the offline copy too.

### 2.2 The Developer app

The Developer app is built for live development:

1. **Metro** - if it is connected to your laptop, it uses your latest local code.
2. **Development-channel EAS Update** - if Metro is unavailable, it can fall back to its configured development channel.
3. **Built-in APK bundle** - the final fallback.

In practice: **treat the Developer app as live-only.** When Metro stops, it falls back to older code. That is normal, not a bug.

### 2.3 The backend

Backend/API changes are different. Once the backend is deployed, the app receives the new behavior through normal HTTPS requests. No Metro session, OTA, or reinstall is needed for backend-only changes.

### 2.4 Why old code appears

| What you did | What you see | Why |
|---|---|---|
| Developer app, Metro running | New code | Metro serves from your laptop |
| Developer app, Metro closed | Old code | Metro is live-only; it falls back |
| Preview app, first launch after publish | Old code | The update is downloading in the background |
| Preview app, closed and reopened | New code | The downloaded update is now applied |
| Preview app, offline, after applying | New code | The update is stored on the phone |
| Preview app, offline, before applying | Old code | The update was never applied |
| Update crashes on launch | Old code | Expo automatically rolls back |
| Opened Preview but still old | Maybe the Developer app | Check the name under the icon |

**Important:** the current Preview APK already contains the new home screen in its built-in bundle. So even offline, it should show the new design. If you see the old design offline, first check that you opened **AFCON360 Preview**, not **AFCON360 Developer**.

---

## 3. Metro - the fast development loop

### 3.1 What Metro is for

Use Metro while you are writing code. You save a file and the phone updates in about a second. No APK rebuild. No EAS publish.

### 3.2 What you need

- The laptop and phone on the same Wi-Fi, or the phone connected by USB with USB debugging enabled.
- The **AFCON360 Developer** app installed.
- The backend available at `C:\Users\OBED\Desktop\afcon360_app` (the scripts expect it as a sibling folder).

### 3.3 Recommended start (one command)

Open PowerShell and run:

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1
```

What the script does:

1. Starts the local Flask API on port **5000**.
2. Starts Metro on port **8081**.
3. Uses USB if an authorized Android device is available and the Developer app is installed; otherwise shows a QR code for Wi-Fi.
4. Opens the Developer app or asks you to scan the QR.

If it asks you to choose a laptop address, choose the address on the same network as the phone.

### 3.4 The edit loop

1. Open the **AFCON360 Developer** app.
2. Edit any file under `mobile/apps/user/`.
3. Save.
4. Watch the phone update automatically (Fast Refresh).
5. If it does not refresh, shake the phone and choose **Reload**, or press `r` in the Metro window.

### 3.5 Useful options

```powershell
# Metro port 8081 is already in use
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1 -MetroPort 8083

# Force USB
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1 -ConnectionMode Usb

# Force Wi-Fi / hotspot
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1 -ConnectionMode Lan

# Wi-Fi with a known laptop IP
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1 -ConnectionMode Lan -MetroHost "192.168.1.50"

# Clear the Metro cache
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1 -ClearMetroCache

# Check the live Pamoja server without starting local Flask or Metro
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1 -TargetEnvironment Pamoja
```

### 3.6 Metro only

If the API is already running and you only want Metro:

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-metro.ps1 -ConnectionMode Lan -ApiBaseUrl http://192.168.1.50:5000
```

For USB:

```powershell
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-metro.ps1 -ConnectionMode Usb
```

Options:

- `-Port 8083` if 8081 is busy.
- `-ClearCache` to clear the Metro cache.
- `-ApiBaseUrl` is required for LAN mode.

### 3.7 Advanced: manual Metro from the workspace

The Windows scripts set the correct Developer-app identity, update channel, and local API address. If you start Metro manually, set the same variables first:

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile
$env:AFCON360_PREVIEW_BUILD="true"
$env:AFCON360_RELEASE_BUILD="false"
$env:AFCON360_DEVELOPMENT_CLIENT="true"
$env:AFCON360_UPDATE_CHANNEL="user-development-client"
$env:EXPO_PUBLIC_API_BASE_URL="http://192.168.1.50:5000"
pnpm user:start --reset-cache
```

Do not run a bare `pnpm start` in a fresh terminal. Without those variables, the app can resolve to the production identity/channel and point at the live Pamoja API instead of your laptop.

### 3.8 What Metro cannot do

- It cannot make changes permanent.
- It cannot work offline.
- It cannot update native code.
- It cannot update the Preview app.

If you close Metro, the Developer app falls back to older code. That is expected.

---

## 4. EAS Update - the permanent update

### 4.1 What EAS Update is for

EAS Update sends a new JavaScript/TypeScript bundle and assets to an installed app. It is how you update the **Preview** app without rebuilding the APK.

It is persistent: once the update is downloaded and applied, it works offline.

### 4.2 What can and cannot go through EAS Update

| Change | EAS Update? | New APK? |
|---|---|---|
| Screen layout, text, styles, navigation | Yes | No |
| JavaScript/TypeScript business logic | Yes | No |
| Images and compatible assets | Yes | No |
| New native library | No | Yes |
| New permission | No | Yes |
| `app.config.ts` change | No | Yes |
| `eas.json` change | No | Yes |
| `package.json` or lockfile change | No | Yes |
| Native plugin or native code | No | Yes |
| Backend/API only | No app update needed | No |

### 4.3 How code reaches EAS

EAS does not watch GitHub or your laptop. Code reaches EAS only when something uploads it.

There are two uploaders:

1. **Automatic (recommended): GitHub Actions**
   - Merging or pushing to `feat/native-user-app-integration-20261108` triggers the workflow.
   - Workflow file: `.github/workflows/user-preview-ota-update.yml`.
   - It publishes to the `preview` channel.
   - The update message includes the commit SHA.

2. **Manual: your laptop**
   - You run `eas update` from `mobile/apps/user`.
   - It bundles the files currently on disk and uploads them.
   - Useful when you want to test before merging.

The automatic workflow only runs for these paths:

- `mobile/apps/user/app/**`
- `mobile/apps/user/src/**`
- `mobile/apps/user/assets/**`
- `mobile/packages/core/src/**`
- `mobile/packages/core/assets/**`
- `mobile/packages/ui/src/**`
- `mobile/packages/ui/assets/**`

Changes to `app.config.ts`, `eas.json`, `package.json`, lockfiles, or native code do **not** trigger an OTA. Those need a new APK.

### 4.4 Automatic publish after a merge

This is the normal flow:

1. A PR is merged into `feat/native-user-app-integration-20261108`.
2. GitHub Actions runs **User preview OTA update**.
3. The workflow checks out the merged commit, installs dependencies, type-checks, and exports the bundles.
4. It runs `eas update --channel preview --environment preview`.
5. EAS stores the update with runtime `1.0.2`.
6. The phone downloads it on the next online launch and applies it on the following launch.

The latest automatic update is:

- Message: `AFCON360 User preview 17c99d1c...`
- Commit: `17c99d1c` (the merged PR #144)
- Channel: `preview`
- Runtime: `1.0.2`

You do not run anything for this path. The merge is the trigger.

### 4.5 Manual publish

Use this when you want to publish without merging, or when you need to test a local change on the Preview app.

Copy the whole block:

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile\apps\user
$env:AFCON360_PREVIEW_BUILD="true"
$env:AFCON360_RELEASE_BUILD="false"
$env:AFCON360_DEVELOPMENT_CLIENT="false"
$env:AFCON360_UPDATE_CHANNEL="preview"
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
$env:EXPO_PUBLIC_API_BASE_URL="https://www.pamoja.space"
npx eas-cli update --channel preview --environment preview --platform android --message "describe the change" --non-interactive
```

Wait for the CLI to print `Published`.

Then on the phone:

1. Open **AFCON360 Preview** while online.
2. Wait 10-20 seconds.
3. Fully close the app.
4. Reopen it.
5. The new version is now active and will work offline.

If you publish again later, repeat the same two-launch pattern.

### 4.6 Why two launches?

- First launch: the app opens with the current code and downloads the new bundle in the background.
- Second launch: the app opens with the downloaded bundle.
- After the second launch, the bundle is stored on the phone and is used offline.

If you close the app before the download finishes, the second launch may still be old. Open it online again and wait.

### 4.7 If the update does not appear

Check these in order:

1. **Which app are you opening?** It must be **AFCON360 Preview**, not **AFCON360 Developer**.
2. **Is the phone online?** The update downloads only while online.
3. **Did you close and reopen?** The update applies on the next launch.
4. **Is the channel correct?** The Preview app uses `preview`.
5. **Is the runtime correct?** The current non-release runtime is `1.0.2`.
6. **Check the published updates:**

   ```powershell
   cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile\apps\user
   $env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
   npx eas-cli update:list --branch preview --platform android --non-interactive
   ```

   Note: use `--branch preview`, not `--channel preview`, for this CLI command.

7. **Did the update crash?** Expo rolls back to the previous working code. Fix the crash and publish again.

### 4.8 Channels and runtimes

A **channel** is the update stream the app listens to. Publishing to the wrong channel is like putting a letter in the wrong mailbox.

| Build | Channel | Runtime |
|---|---|---|
| AFCON360 Preview | `preview` | `1.0.2` (app version) |
| AFCON360 Developer | `user-development-client` | `1.0.2` (app version) |
| `dev-apk` profile | `user-development` | `1.0.2` (app version) |
| Production | `production` | native fingerprint |

A **runtime** is a compatibility tag. An app only accepts updates built for its runtime.

- Non-release builds (preview/development) use the app version: currently `1.0.2`.
- Production uses the native fingerprint.

**Important:** if you change native dependencies, bump `version` in `mobile/apps/user/app.config.ts` (for example `1.0.2` to `1.0.3`), build a new APK, and publish a new update. If you do not bump the version, the runtime stays the same and an old OTA could be served to a binary it no longer matches.

---

## 5. When you need a new APK

Build a new APK when any of these change:

- Native dependencies or Expo SDK version.
- Android permissions.
- Native plugins.
- Native code.
- `app.config.ts`.
- `eas.json`.
- `package.json` or the lockfile.
- The app version (when native compatibility changes).

### 5.1 Preview APK

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile\apps\user
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
npx eas-cli build --profile preview --platform android
```

The preview profile sets:

- App name: AFCON360 Preview
- Package: `space.pamoja.afcon360.user.preview`
- Channel: `preview`
- Runtime: app version (`1.0.2`)
- Distribution: internal APK

### 5.2 Developer APK (Metro client)

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile\apps\user
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
npx eas-cli build --profile development --platform android
```

The development profile sets:

- App name: AFCON360 Developer
- Package: `space.pamoja.afcon360.user.preview.dev`
- Channel: `user-development-client`
- Runtime: app version (`1.0.2`)
- Distribution: internal APK

### 5.3 Production build

Only with release approval:

```powershell
npx eas-cli build --profile production --platform android
```

Production uses the `production` channel and the native fingerprint runtime. Do not use this for everyday testing.

### 5.4 After installing a new APK

- The APK contains a new built-in bundle. That becomes the offline fallback.
- If the runtime changed, publish a new EAS Update for the new runtime.
- If the runtime did not change, existing compatible updates can still be served.

---

## 6. Recommended daily workflow

| Goal | What to do |
|---|---|
| See changes while coding | Developer app + Metro |
| Put changes on the Preview app | Merge/push (CI publishes) or run manual `eas update`; then open Preview twice |
| Test offline behavior | Apply the update first, then turn off Wi-Fi/data and reopen |
| Hand the phone to a tester | Use the Preview app; it works without the laptop |
| Change a native library/permission/config | Build a new APK, install it, then publish an OTA if needed |
| Production release | Production build with approval; not covered by the everyday flow |

The simple rule:

- **Metro = now, while you code.**
- **EAS Update = later, on the installed Preview app.**
- **New APK = only when native things change.**

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `pnpm start` says "No package.json" | Wrong folder | Run from `mobile` or `mobile/apps/user`, or use the Windows scripts |
| `ERR_PNPM_NO_SCRIPT_OR_SERVER` | You are in the backend folder | The backend has no `start` script; use the mobile folder |
| `ERR_PNPM_NO_IMPORTER_MANIFEST_FOUND` | You are in the repo root | `cd` into `mobile` |
| Metro port 8081 is in use | Another Metro/server is running | Use `-MetroPort 8083` or stop the old process |
| Phone cannot connect to Metro | Different network, firewall, or USB not set up | Same Wi-Fi; Private network; ports 5000/8081; use `-ConnectionMode Usb` |
| Old code after closing Metro | You are in the Developer app | Expected; use the Preview app for persistence |
| Preview still shows old code after publish | Update not applied | Open online, wait, close, reopen; check channel/runtime |
| CI did not publish my change | Path filter or native-only change | Merge a JS/TS/asset change; native changes need an APK |
| EAS says no update / wrong runtime | Channel or runtime mismatch | Preview = `preview` + `1.0.2`; check `app.config.ts` |
| App crashes after an OTA | Bad update | Expo rolls back; fix and republish |
| Preview has no Metro option | By design | Use the Developer app for Metro |
| `expo install --check` says packages need updating | Dependency drift | Run `npx expo install --check`; native changes need a rebuild |

---

## 8. Command cheat sheet

### Start everything (Flask + Metro + device)

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1
```

### Metro only (LAN)

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-metro.ps1 -ConnectionMode Lan -ApiBaseUrl http://192.168.1.50:5000
```

### Metro only (USB)

```powershell
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-metro.ps1 -ConnectionMode Usb
```

### Clear Metro cache

```powershell
powershell -ExecutionPolicy Bypass -File .\mobile\scripts\windows\start-user-dev.ps1 -ClearMetroCache
```

### Publish a preview update manually

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile\apps\user
$env:AFCON360_PREVIEW_BUILD="true"
$env:AFCON360_RELEASE_BUILD="false"
$env:AFCON360_DEVELOPMENT_CLIENT="false"
$env:AFCON360_UPDATE_CHANNEL="preview"
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
$env:EXPO_PUBLIC_API_BASE_URL="https://www.pamoja.space"
npx eas-cli update --channel preview --environment preview --platform android --message "describe the change" --non-interactive
```

### List preview updates

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile\apps\user
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
npx eas-cli update:list --branch preview --platform android --non-interactive
```

### Build a preview APK

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile\apps\user
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
npx eas-cli build --profile preview --platform android
```

### Build a developer APK

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile\apps\user
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
npx eas-cli build --profile development --platform android
```

### Check the app configuration before publishing

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile\apps\user
$env:AFCON360_PREVIEW_BUILD="true"
$env:AFCON360_RELEASE_BUILD="false"
$env:AFCON360_DEVELOPMENT_CLIENT="false"
$env:AFCON360_UPDATE_CHANNEL="preview"
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
npx expo config --type public
```

Look for:

- `name: AFCON360 Preview`
- `android.package: space.pamoja.afcon360.user.preview`
- `runtimeVersion` policy: `appVersion` (resolves to `1.0.2`)
- `updates.requestHeaders["expo-channel-name"]: preview`

---

## 9. Plain-English glossary

- **Metro** - a server on your laptop that sends your latest JavaScript to the Developer app.
- **Bundler** - the tool that packs your code into a bundle the app can run.
- **APK** - the installable Android app file.
- **Built-in bundle** - the code frozen inside the APK at build time.
- **OTA (Over-The-Air) update** - a new JavaScript bundle downloaded from EAS. It is not a new APK.
- **EAS Update** - the cloud service that stores and serves OTA bundles.
- **EAS Build** - the cloud service that builds APKs from your source.
- **Channel** - the name of the update stream the app listens to.
- **Runtime version** - the compatibility tag; an app only accepts updates built for its runtime.
- **Fast Refresh** - Metro applies your saved changes to the running app without a manual reload.

---

## 10. What changed and why

- **Preview and development builds use the app version as the runtime** (`1.0.2`). This prevents a stale local `node_modules` from blocking an internal APK build. Production keeps the native fingerprint for safety.
- **Bump the app version when native dependencies change**, then build a new APK and publish a new update. Otherwise the runtime stays the same and an old OTA could reach a binary it no longer matches.
- **Merging to the canonical branch publishes the preview OTA automatically** through GitHub Actions. You do not run anything for that path.
- **The Preview app intentionally has no Metro controls.** It is the standalone/testing app. The Developer app is the Metro app.
- **The current Preview APK already contains the new home screen in its built-in bundle.** If offline shows the old design, check which app you opened.
