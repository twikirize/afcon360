# Mobile Pre-Flight Check

Run this before any APK build and before any OTA publish, for the User or Driver app.

Every step names a command and the result that counts as a pass. A step you did not run is a fail, not a maybe. The checks below are the ones actually exercised on 27 November 2026 for the User app 1.0.3 release.

This is the **release** gate. The commit gate is `docs/engineering/PRE_PR_CHECKS.md`, and the build/publish procedure is `update_apk.md` in this folder. If you are only pushing code, you need the first of those and can stop there; come back here when the question becomes "which binary does this change require, and to which channel does it go?".

Run everything from `mobile/` inside the checkout that contains it (`C:\Users\OBED\Desktop\afcon360-user-dev`). The Flask checkout at `C:\Users\OBED\Desktop\afcon360_app` — prompt `(.venv) PS C:\Users\OBED\Desktop\afcon360_app>` — has no `mobile/` directory and cannot build or publish either app.

---

## 1. Stand in the right directory

All commands run from `mobile/` unless the step says otherwise.

The repository root is **not** a pnpm workspace. Running `pnpm --filter ...` there fails, and worse, a stale copy of the project (`_mobile_backup_*`) can answer the call and resolve a completely different `expo` binary.

- [ ] `pnpm --version` prints the workspace package manager (`pnpm@10.12.4`).
- [ ] `pnpm user:typecheck` actually executes a script rather than erroring with "No projects matched".

## 2. Set the identity variables

Dynamic configuration means the app's identity is computed from these variables. Unset variables do not error; they silently produce a different app.

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile\apps\user
$env:AFCON360_PREVIEW_BUILD="true"
$env:AFCON360_RELEASE_BUILD="false"
$env:AFCON360_DEVELOPMENT_CLIENT="false"
$env:AFCON360_UPDATE_CHANNEL="preview"
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
$env:EXPO_PUBLIC_API_BASE_URL="https://www.pamoja.space"
```

| Variable | What it decides | If missing |
|---|---|---|
| `AFCON360_PREVIEW_BUILD` | `.preview` package suffix, "AFCON360 Preview" name, preview plugin, server switcher | Production identity: `space.pamoja.afcon360.user`, channel `production` |
| `AFCON360_RELEASE_BUILD` | Runtime policy and the HTTPS/no-loopback assertion | `appVersion` runtime, and the production API guard does not run |
| `AFCON360_DEVELOPMENT_CLIENT` | Dev-client build versus standalone | Standalone app |
| `AFCON360_UPDATE_CHANNEL` | The channel name the app requests updates from | `preview` |
| `AFCON360_USER_EAS_PROJECT_ID` | `extra.eas.projectId` and `updates.url` | Local `eas` commands prompt to link a project they cannot write, then fail |
| `EXPO_PUBLIC_API_BASE_URL` | API base URL baked into the bundle | `https://www.pamoja.space` |

Never answer the "Configure this project?" prompt by hand, and never continue a build after it appears.

## 3. Prove the identity before trusting the terminal

```powershell
pnpm exec expo config --json | ConvertFrom-Json | Select-Object name,version,@{n='pkg';e={$_.android.package}},@{n='policy';e={$_.runtimeVersion.policy}},@{n='channel';e={$_.updates.requestHeaders.'expo-channel-name'}}
```

Expected for the preview lane:

| Field | Expected |
|---|---|
| `name` | `AFCON360 Preview` |
| `android.package` | `space.pamoja.afcon360.user.preview` |
| `version` | the version you intend to ship |
| `runtimeVersion.policy` | `appVersion` |
| channel header | `preview` |

Do not continue if any row differs from what you intend to ship.

## 4. Code gates

The seven commands in `docs/engineering/PRE_PR_CHECKS.md` are the gate for shipping as well as for pushing. Run them, in this tree, before continuing; they are not duplicated here so that the two documents cannot drift apart.

Release-specific additions to those seven:

- [ ] `pnpm driver:typecheck` also exits 0, if the driver app was touched.
- [ ] Any export output directory created inside the repository is deleted before committing. `.ota-check` and `dist` are **not** covered by `mobile/.gitignore`; exporting to `$env:TEMP` avoids the problem entirely.

**Gates are only meaningful if the files you think you wrote exist.** After a long edit session, confirm the new symbols are actually in the tree before reading a green result as proof:

```powershell
Get-ChildItem -Recurse -Include *.tsx src | Select-String -Pattern "PamojaMark|PamojaTabBar" -List
```

## 5. Decide: APK or OTA

Decide before you build, not after.

| Change | APK | OTA |
|---|---|---|
| Screen layout, text, styles, navigation, business logic, images | No | Yes |
| New or removed native module, native plugin, native code | **Yes** | No |
| Android permission or `app.config.ts` change | **Yes** | No |
| `eas.json`, `package.json`, lockfile, Expo SDK version | **Yes** | No |
| Backend/API only | No | No |

If any APK-only item changed:

- [ ] Bump `version` in `apps/user/app.config.ts`.
- [ ] Build and install the APK in the same step.
- [ ] Never bump `version` without a matching build. See `README.md`, "Runtime version discipline".

`android.versionCode` in `app.config.ts` is ignored because `cli.appVersionSource` is `remote`; EAS auto-increments the remote value.

## 6. Before publishing an OTA

- [ ] `version` in `app.config.ts` is unchanged since the installed binary was built.
- [ ] The channel's runtime matches that version:

  ```powershell
  eas channel:view preview
  ```

- [ ] Publish names channel, environment and platform explicitly:

  ```powershell
  eas update --channel preview --environment preview --platform android --message "describe the change"
  ```

- [ ] `eas update:list --branch preview --platform android` lists a group whose runtime equals the installed binary's runtime. Note: `update:list` takes `--branch`, not `--channel`.
- [ ] The device shows the new code after two launches (download on the first, apply on the second).

## 7. Before and after building an APK

- [ ] Sections 1-4 are green, including every command in `docs/engineering/PRE_PR_CHECKS.md`.
- [ ] `version` was bumped only because a native change required it.
- [ ] The build reaches `finished`. An empty `Application Archive URL` means "still running", not "failed".
- [ ] The build metadata shows the intended identity and runtime:

  ```powershell
  eas build:list --platform android --limit 1
  ```

  Check `Runtime Version`, `Version`, `Version code` and `Commit`.
- [ ] Install the APK and launch it once, while watching the first screen paint. This is the only proof that new native modules link. Typecheck and bundling cannot prove it.
- [ ] Record the build ID, runtime, version code and artifact URL in the release report.

## 8. Known false greens

| What you see | What is actually true |
|---|---|
| Typecheck and export pass, but the UI is unchanged | The new files were never written or never saved. Grep for the symbols. |
| `eas update` prints a published group and exits 0, nothing changes on the phone | The update's runtime does not match any installed binary, or the channel is wrong. A green publish is not delivery. |
| PowerShell shows `node.exe : ... NativeCommandError` after an `eas` command | Expo's spinner writes to stderr; PowerShell wraps it as an error. The result printed below it is valid. |
| `eas build:list` fails with "Cannot automatically write to dynamic config" | Missing `AFCON360_USER_EAS_PROJECT_ID`. The project is not broken and nothing was unlinked. |
| A chained command exits 1 with no output | `expo export` combined with cleanup in one pipeline is unreliable. Run it alone. |
| The install prompt calls the APK an "update" | Same package name and a higher version code: Android replaces the binary in place. It is still a full APK, not an OTA. |
| `expo-doctor` warns about a duplicate `expo-modules-jsi` | Pre-existing in this workspace. Not part of a build's pass criteria. |

## 9. Sign-off

| Field | Value |
|---|---|
| Date | |
| App and lane | User preview / Driver preview / production |
| Gates | typecheck, driver typecheck, navigation, export |
| Version / runtime | |
| Build ID or update group | |
| Installed and launched on device | yes / no |
| Verified by | |
