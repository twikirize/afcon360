# Mobile Pre-PR and Release Checklist (AFCON360)

**Part A must pass before every commit or PR. Part B must pass before any APK build or OTA publish.** The CI workflow runs Part A's exact commands — failures there will block the PR.

> The file name is unchanged so existing references keep working. Part B was merged here from `mobile/docs/PRE_CHECK.md`, which no longer exists.

## Where these commands run

| Folder | What it is | Mobile commands |
|---|---|---|
| `C:\Users\OBED\Desktop\afcon360-user-dev` | The checkout that contains `mobile/` (the pnpm workspace with the User and Driver apps) | **Yes** — all of them |
| `C:\Users\OBED\Desktop\afcon360_app` | The Flask/web checkout of the same repository. A prompt of `(.venv) PS C:\Users\OBED\Desktop\afcon360_app>` means you are here | **No** — it has no `mobile/` directory, so every command below fails |

Run from the `mobile/` directory. The repository root is **not** a pnpm workspace: `pnpm --filter ...` there fails, and a stale copy of the project (`_mobile_backup_*`) can answer the call and run an entirely different `expo` binary.

## The mobile documents

| Document | Moment | Question it answers |
|---|---|---|
| `docs/engineering/PRE_PR_CHECKS.md` (this file) | Part A before every commit or PR; Part B before a build or publish | Is this tree safe to push — and safe to ship, to whom? |
| `mobile/docs/update_apk.md` | During the build or publish itself | What are the exact steps? |
| `AGENTS_BRANCH_RULES.md` (in both checkouts) | Before any branch, commit or push | Where may this work land? |

---

## Required Local Commands (run from `mobile/` directory)

```bash
# 1. Navigation contracts — validates native routes and external handoffs
node scripts/check-navigation-contracts.mjs

# 2. Offline foundation — verifies SQLite, SQLCipher, cache, auth wiring
node scripts/verify-user-offline-foundation.mjs

# 3. APK metadata — self-tests the signed APK parser
node scripts/verify-user-dev-apk-metadata.mjs --self-test

# 4. TypeScript — strict type checking for user app
pnpm user:typecheck

# 5. Android bundle export — proves the app bundles for Android
pnpm --filter @afcon360/user-app exec expo export --platform android --output-dir "$env:TEMP\afcon360-user-android"

# 6. iOS bundle export — proves the app bundles for iOS
pnpm --filter @afcon360/user-app exec expo export --platform ios --output-dir "$env:TEMP\afcon360-user-ios"

# 7. Development delivery contract — verifies Metro/EAS/OFB fallback config
$env:AFCON360_PREVIEW_BUILD = "true"
$env:AFCON360_RELEASE_BUILD = "false"
$env:AFCON360_DEVELOPMENT_CLIENT = "true"
$env:AFCON360_UPDATE_CHANNEL = "user-development-client"
$env:EXPO_PUBLIC_API_BASE_URL = "http://127.0.0.1:5000"
$env:AFCON360_USER_EAS_PROJECT_ID = "00000000-0000-4000-8000-000000000001"
pnpm --filter @afcon360/user-app exec expo config --json 2>&1 | Out-File -Encoding utf8 "$env:TEMP\afcon360-user-dev-delivery-config.json"
node scripts/verify-user-dev-delivery-contract.mjs "$env:TEMP\afcon360-user-dev-delivery-config.json"
```

**All seven must pass.** Do not push if any fail.

`pnpm navigation:check` is an alias for command 1 and is the only one exposed as an npm script; the other three contract scripts are run directly with `node`. Command 7 is meaningless without the five variables above, because app identity is computed from them and unset variables silently produce the production identity instead of failing.

---

## When to Run These

- After any change to: navigation, routing, screen components, `expo-router` usage, `Linking`/`WebBrowser` calls
- After adding/modifying screen files under `apps/user/app/**/*.tsx` or `apps/user/src/components/**/*.tsx`
- After modifying `mobile/scripts/check-navigation-contracts.mjs`
- After any TypeScript/React Native code change
- After adding/removing bottom navigation tabs (also requires updating `check-navigation-contracts.mjs` and the E2E tests)
- After any change to `app.config.ts`, `eas.json`, the lockfile, or a native dependency — those are release-affecting, so also run Part B

---

## Tab Bar and Navigation Structure

The tab bar is custom: `apps/user/app/(tabs)/_layout.tsx` declares the screens, and `apps/user/src/components/home/PamojaTabBar.tsx` renders them. There is no `tabIcons`/`tabLabels` record in `_layout.tsx` — labels and Ionicons live in `TAB_LABELS` and `TAB_ICONS` inside `PamojaTabBar.tsx`.

| Position | Screen | Title | Icon source |
|---|---|---|---|
| 1 | `index` | Home | `TAB_ICONS.index` → Ionicons `home` |
| 2 | `activity` | Activity | `TAB_ICONS.activity` → Ionicons `clipboard-outline` |
| 3 | `explore` | Explore | Not an icon: the `PamojaMark` SVG in the gold ring (`renderFab`) |
| 4 | `wallet` | Wallet | `TAB_ICONS.wallet` → Ionicons `wallet` |
| 5 | `account` | Account | `TAB_ICONS.account` → Ionicons `person-outline` |

`explore` is rendered as the centre FAB, not by `renderItem`. Changing tab order therefore means editing **two** files and the contract script — not one.

**Navigation flow checks:** the checker is the source of truth for the handoff list, and it currently asserts 13 explicitly labelled website handoffs plus the internal native routes. Do not hand-maintain a parallel list here; a green `navigation:check` means every string the checker knows about is still present where it expects it. When you move a navigation call into a different component, the checker fails until its expectations are moved too — that is the intended behaviour.

Note that the checker validates *literals*, not behaviour. A route string can be present and still be attached to the wrong handler. Typecheck plus the checker do not prove the tab bar navigates; only a launch on a device does.

---

## Common Failure Patterns & Fixes

### Navigation Contract Failures

**Error:** `Required native route ... is missing or changed: apps/user/app/(tabs)/index.tsx`

**Cause:** The checker expects navigation strings in `index.tsx` but they moved to `HomeServiceGrid.tsx`, `WalletCard.tsx`, or `explore.tsx`.

**Fix:** Update `mobile/scripts/check-navigation-contracts.mjs`:
- Remove stale expectations from `index.tsx`
- Add expectations for the component that now owns the route

```javascript
// HomeServiceGrid owns service destinations
["apps/user/src/components/home/HomeServiceGrid.tsx", "destination: '/(service)/ride'"],
["apps/user/src/components/home/HomeServiceGrid.tsx", "router.push(service.destination as any)"],

// WalletCard owns wallet navigation
["apps/user/src/components/home/WalletCard.tsx", "router.push('/(tabs)/wallet' as any)"],
```

### TypeScript Failures

**Error:** `Property 'absoluteFillObject' does not exist...`

**Fix:** Use `StyleSheet.absoluteFill` instead of `StyleSheet.absoluteFillObject`.

### Custom tabBar Failures

**Error:** `Property 'navigation' does not exist on type 'BottomTabBarProps'`

**Cause:** expo-router's vendored bottom tabs pass `state`, `descriptors`, `emitter`, `navigateToTab` and `insets`. There is no `navigation` member, and no value for it at runtime.

**Fix:** Use `emitter.emit({ type: 'tabPress', target: route.key, canPreventDefault: true })` then `navigateToTab(route.key)`. Never silence this with `as any`: the type error is the only warning before a white screen on every tab press.

### Bundle Export Failures

**Error:** `Unable to resolve module ...`

**Fix:** Check `require()` paths for local assets (e.g., `require('../../../assets/pamoja-hero.jpeg')`). Ensure the file exists at that relative path from the importing file.

---

## New File Checklist

Before adding any `.tsx` or `.js` file:

1. **Navigation ownership** — If the file handles routing (`router.push`, `Linking.openURL`, `WebBrowser.openBrowserAsync`), add its expectations to `check-navigation-contracts.mjs` in both `approved` (external) and `nativeInternalRoutes` (internal) arrays.

2. **Route guarding** — If it's a new authenticated screen, place it under `apps/user/app/(service)/` or `apps/user/app/(tabs)/` — never at the root `apps/user/app/`.

3. **Public root routes** — If adding a file at `apps/user/app/*.tsx`, add it to `publicRootRouteFiles` in the checker.

4. **TypeScript** — Run `pnpm user:typecheck` after adding the file.

5. **Exports** — Run both Android and iOS exports to verify bundling.

6. **Bottom tab changes** — If adding/removing tabs:
   - `(tabs)/_layout.tsx`: add/remove the `Tabs.Screen` entry
   - `PamojaTabBar.tsx`: update `TAB_LABELS` and `TAB_ICONS`, the `LEFT_TABS`/`RIGHT_TABS` split, and the `TAB_HREF` fallback map
   - `check-navigation-contracts.mjs`: update `nativeInternalRoutes`
   - E2E tests (`verify-user-authenticated-journey.py`): update tab navigation

7. **New native module** — Typecheck and bundling cannot prove it links. It requires an APK build. Run Part B.

---

## Part B — Shipping gate (APK build or OTA publish)

Part A proves the tree compiles. Part B decides **which binary** carries the change and **which channel** receives it.

### B1. Set the identity variables

Identity is computed from these variables. Unset variables do not error; they silently produce a different app.

```powershell
cd C:\Users\OBED\Desktop\afcon360-user-dev\mobile\apps\user
$env:AFCON360_PREVIEW_BUILD="true"
$env:AFCON360_RELEASE_BUILD="false"
$env:AFCON360_DEVELOPMENT_CLIENT="false"
$env:AFCON360_UPDATE_CHANNEL="preview"
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
$env:EXPO_PUBLIC_API_BASE_URL="https://www.pamoja.space"
```

| Variable | Decides | If missing |
|---|---|---|
| `AFCON360_PREVIEW_BUILD` | `.preview` package suffix, "AFCON360 Preview" name, preview plugin, server switcher | Production identity: `space.pamoja.afcon360.user`, channel `production` |
| `AFCON360_RELEASE_BUILD` | Runtime policy and the HTTPS/no-loopback assertion | `appVersion` runtime, and the production API guard does not run |
| `AFCON360_DEVELOPMENT_CLIENT` | Dev-client build versus standalone | Standalone app |
| `AFCON360_UPDATE_CHANNEL` | The channel the app requests updates from | `preview` |
| `AFCON360_USER_EAS_PROJECT_ID` | `extra.eas.projectId` and `updates.url` | Local `eas` commands prompt to link a project they cannot write, then fail |
| `EXPO_PUBLIC_API_BASE_URL` | API base URL baked into the bundle | `https://www.pamoja.space` |

Never answer the "Configure this project?" prompt by hand, and never continue a build after it appears.

### B2. Prove the identity before trusting the terminal

```powershell
pnpm exec expo config --json | ConvertFrom-Json | Select-Object name,version,@{n='pkg';e={$_.android.package}},@{n='policy';e={$_.runtimeVersion.policy}},@{n='channel';e={$_.updates.requestHeaders.'expo-channel-name'}}
```

| Field | Expected on the preview lane |
|---|---|
| `name` | `AFCON360 Preview` |
| `android.package` | `space.pamoja.afcon360.user.preview` |
| `version` | the version you intend to ship |
| `runtimeVersion.policy` | `appVersion` |
| channel header | `preview` |

Do not continue if any row differs from what you intend to ship.

### B3. Decide: APK or OTA

Decide before you build, not after.

| Change | APK | OTA |
|---|---|---|
| Screen layout, text, styles, navigation, business logic, images | No | Yes |
| New or removed native module, native plugin, native code | **Yes** | No |
| Android permission or `app.config.ts` change | **Yes** | No |
| `eas.json`, `package.json`, lockfile, Expo SDK version | **Yes** | No |
| Backend/API only | No | No |

If any APK-only item changed: bump `version` in `apps/user/app.config.ts`, then build and install the APK in the same step. Never bump `version` without a matching build — a JS-only bump publishes to a runtime no installed binary has, which is a silent no-op. See `mobile/README.md`, "Runtime version discipline".

`android.versionCode` in `app.config.ts` is ignored because `cli.appVersionSource` is `remote`; EAS increments the remote value.

### B4. Before publishing an OTA

- [ ] `version` in `app.config.ts` is unchanged since the installed binary was built.
- [ ] The channel's runtime matches that version: `eas channel:view preview`.
- [ ] The publish names channel, environment and platform explicitly:

  ```powershell
  eas update --channel preview --environment preview --platform android --message "describe the change"
  ```

- [ ] `eas update:list --branch preview --platform android` lists a group whose runtime equals the installed binary's. It takes `--branch`, not `--channel`.
- [ ] The device shows the new code after **two** launches. `checkAutomatically: "ON_LOAD"` with `fallbackToCacheTimeout: 0` downloads on the first launch and applies on the second, so a single reopen legitimately shows nothing.

### B5. Before and after building an APK

- [ ] Part A and B1-B3 are green.
- [ ] `version` was bumped only because a native change required it.
- [ ] The build reaches `finished`. An empty `Application Archive URL` means "still running", not "failed".
- [ ] `eas build:list --platform android --limit 1` shows the intended `Runtime Version`, `Version`, `Version code` and `Commit`.
- [ ] The APK is installed and launched once while watching the first screen paint. That is the only proof that new native modules link; typecheck and bundling cannot show it.
- [ ] Build ID, runtime, version code and artifact URL are recorded in the release report.

### B6. Release sign-off

| Field | Value |
|---|---|
| Date | |
| App and lane | User preview / Driver preview / production |
| Gates | Part A seven commands, plus Part B checks |
| Version / runtime | |
| Build ID or update group | |
| Installed and launched on device | yes / no |
| Verified by | |

---

## Known False Greens

| What you see | What is actually true |
|---|---|
| Typecheck and export pass, but the UI is unchanged | The new files were never written or never saved. Grep for the symbols before trusting the result. |
| A green result after a long edit session | Gates only prove the tree as it exists. Confirm the symbols you intended are present. |
| PowerShell shows `node.exe : ... NativeCommandError` | Expo's spinner writes to stderr; PowerShell wraps it as an error. The result printed below it is valid. |
| A chained command exits 1 with no output | `expo export` combined with cleanup in the same pipeline is unreliable. Run it alone. |
| `expo-doctor` warns about a duplicate `expo-modules-jsi` | Pre-existing in this workspace. Not part of a gate's pass criteria. |
| `eas update` prints a published group and exits 0, but the phone is unchanged | The group's runtime matches no installed binary, or the channel is wrong. A green publish is not delivery. |
| `eas build:list` fails with "Cannot automatically write to dynamic config" | Missing `AFCON360_USER_EAS_PROJECT_ID`. Nothing was unlinked and the project is not broken. |
| The install prompt calls the APK an "update" | Same package name and a higher version code, so Android replaces the binary in place. It is still a full APK, not an OTA. |

---

## Optional Helper Script

Not committed. If added, it must be reviewed like any other tooling and kept in sync with the seven commands above.

```javascript
import { spawnSync } from "node:child_process";

const checks = [
  ["node", ["scripts/check-navigation-contracts.mjs"]],
  ["node", ["scripts/verify-user-offline-foundation.mjs"]],
  ["node", ["scripts/verify-user-dev-apk-metadata.mjs", "--self-test"]],
  ["pnpm", ["user:typecheck"]],
  ["pnpm", ["--filter", "@afcon360/user-app", "exec", "expo", "export", "--platform", "android", "--output-dir", process.env.TEMP + "\\afcon360-user-android"]],
  ["pnpm", ["--filter", "@afcon360/user-app", "exec", "expo", "export", "--platform", "ios", "--output-dir", process.env.TEMP + "\\afcon360-user-ios"]],
];

for (const [cmd, args] of checks) {
  console.log(`\n=== ${cmd} ${args.join(" ")} ===`);
  const result = spawnSync(cmd, args, { stdio: "inherit", shell: true, cwd: "mobile" });
  if (result.status !== 0) {
    console.error(`\nFAILED: ${cmd} ${args.join(" ")}`);
    process.exit(1);
  }
}
console.log("\nAll pre-PR checks passed");
```

---

## CI Workflow Reference

- `.github/workflows/mobile-workspace.yml` runs the contract scripts (`check-navigation-contracts`, `verify-user-offline-foundation`, `verify-user-dev-apk-metadata --self-test`, `verify-user-dev-delivery-contract`) and both platform exports.
- `.github/workflows/user-preview-ota-update.yml` exports Android and iOS before publishing an OTA.

A failure at any step stops the pipeline. The ~3-5 minute runtime you see in CI is these same commands executing.

**Do not rely on CI to catch issues.** Run locally first.
