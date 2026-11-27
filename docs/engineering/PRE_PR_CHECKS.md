# Pre-PR Testing Checklist for AFCON360 Mobile

**Every agent must run these checks locally before pushing a PR.** The CI workflow runs these exact commands — failures here will block the PR.

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

---

## When to Run These

- After any change to: navigation, routing, screen components, `expo-router` usage, `Linking`/`WebBrowser` calls
- After adding/modifying screen files under `apps/user/app/**/*.tsx` or `apps/user/src/components/**/*.tsx`
- After modifying `mobile/scripts/check-navigation-contracts.mjs`
- After any TypeScript/React Native code change
- After adding/removing bottom navigation tabs (requires updating `check-navigation-contracts.mjs` and E2E tests)

---

## Deep Navigation Validation (5-Tab Structure)

After any navigation change, verify the complete 5-tab structure works:

| Tab | Route | Icon | Key Actions to Verify |
|-----|-------|------|----------------------|
| 1. Home | `index` | `home` | Hero banner, OurServicesHeader, HomeServiceGrid, WalletCard, BookingsCard |
| 2. Explore | `explore` | `explore` | Transport (Book a ride), Accommodation (Find and book a stay), Events, Tourism (website handoff) |
| 3. Activity | `activity` | `event-available` | Ride status, My Events list |
| 4. Wallet | `wallet` | `account-balance-wallet` | Balance, Top Up, transaction history |
| 5. Account | `account` | `person-outline` | Profile, Settings, Sign out |

**Navigation flow checks:**
- Home → View all → Explore (same screen as tab 2)
- Explore → Book a ride → native ride screen
- Explore → Find and book a stay → native stays screen  
- Explore → Discover events and tickets → native events screen
- Explore → Explore tourism on website → WebBrowser handoff
- Account → Home → Explore → back to Account (tab bar persistence)
- Android Back from native screens returns to Explore tab

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

6. **Bottom tab changes** — If adding/removing tabs in `(tabs)/_layout.tsx`:
   - Update `tabIcons` and `tabLabels` records
   - Add/remove `Tabs.Screen` entries
   - Update `check-navigation-contracts.mjs` with new `nativeInternalRoutes`
   - Update E2E tests (`verify-user-authenticated-journey.py`) for new tab navigation

---

## Quick Verification Script

Save as `mobile/scripts/pre-pr-check.mjs` (optional helper):

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
    console.error(`\n❌ FAILED: ${cmd} ${args.join(" ")}`);
    process.exit(1);
  }
}
console.log("\n✅ All pre-PR checks passed");
```

Run: `node mobile/scripts/pre-pr-check.mjs` from repo root.

---

## CI Workflow Reference

The GitHub Actions workflow (`.github/workflows/*.yml`) runs these exact steps in order. A failure at any step stops the pipeline. The ~3-5 minute runtime you see in CI is these same commands executing.

**Do not rely on CI to catch issues.** Run locally first.