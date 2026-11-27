# AFCON360 User App — Dev Client Handover Document

**Last Updated:** 2026-11-18  
**Branch:** `feat/user-offline-first-foundation-20261117`  
**Commit:** `10d858ba` ("Fix user app component imports and ticket purchase types")  
**EAS Build:** `2a4560c8-0dd5-4f3f-9f93-18d24e307625` (dev client v10, versionCode 10, versionName 1.0.2)

---

## 1. Quick Start for New Agent/Engineer

### Prerequisites
- Node.js (with corepack/pnpm)
- Android SDK (`adb` in PATH)
- EAS CLI (`npx eas-cli`)
- Windows PowerShell

### One-Command Setup
```powershell
# 1. Start Metro (LAN mode for wireless Fast Refresh)
$env:AFCON360_PREVIEW_BUILD="true"; $env:AFCON360_RELEASE_BUILD="false"
npx expo start --dev-client --host lan --port 8081

# 2. In another terminal, start Flask API
cd C:\Users\OBED\Desktop\afcon360_app
.\.venv\Scripts\python.exe app.py

# 3. On phone: install dev client APK → open app → Account → Connection settings
#    Enter API: http://<laptop-ip>:5000
#    Enter Metro: http://<laptop-ip>:8081
```

---

## 2. Artifacts & Locations

| Artifact | Location | Notes |
|----------|----------|-------|
| Dev Client APK (v10) | `https://expo.dev/artifacts/eas/mDEIE1100OK5oPaPFMs7XYrpuVw2sVvIirdhG1USaLg.apk` | Direct download |
| Local APK copy | `C:\Users\OBED\AppData\Local\Temp\opencode\afcon360-user-v10-devclient.apk` | 295 MB |
| Metro log (LAN) | `C:\Users\OBED\AppData\Local\Temp\opencode\metro-lan.log` | |
| Metro log (localhost) | `C:\Users\OBED\AppData\Local\Temp\opencode\metro.log` | |
| Flask log | Console where `app.py` runs | |
| EAS Build URL | https://expo.dev/accounts/twikirizeo/projects/afcon360-user/builds/2a4560c8-0dd5-4f3f-9f93-18d24e307625 | |
| EAS Project ID | `20708e30-4640-4b88-9615-38412f47e811` | Required for `eas build` |

---

## 3. Build Process (Reproducible)

### EAS Development Build
```bash
# Set env vars (PowerShell)
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
$env:AFCON360_PREVIEW_BUILD="true"
$env:AFCON360_RELEASE_BUILD="false"

# Build
npx eas-cli build --profile development --platform android --non-interactive

# Profile: development → developmentClient: true, internal distribution, preview env
# Auto-increments versionCode
```

### Local Verification Before Build
```bash
# TypeCheck
corepack pnpm --filter @afcon360/user-app run typecheck

# Expo export (Android bundle test)
corepack pnpm --filter @afcon360/user-app exec expo export --platform android --output-dir "$env:TEMP\opencode\expo-export-check"
```

---

## 4. Runtime Architecture

### Ports & Services
| Service | Port | Binding | Access |
|---------|------|---------|--------|
| Metro (JS Bundler) | 8081 | `0.0.0.0` (LAN) | Phone via hotspot |
| Flask API | 5000 | `0.0.0.0` | Phone via hotspot |
| ADB Reverse | 8081 | `127.0.0.1` | USB fallback |

### Network Topology (Hotspot-Agnostic)
```
┌─────────────┐     Hotspot/Wi-Fi      ┌─────────────┐
│   Phone     │ ◄─────────────────────► │   Laptop    │
│  (Dev App)  │   API: 192.168.x.x:5000 │  (Flask)    │
│             │   Metro: 192.168.x.x:8081│             │
└─────────────┘                         └─────────────┘
       ▲                                        │
       │ USB (fallback)                         │
       └──────── adb reverse tcp:8081 ─────────┘
```

**Key Insight:** Both Metro (8081) and Flask (5000) bind to `0.0.0.0`. The phone reaches them via the laptop's current hotspot IP. No hardcoded IPs needed — the server-settings page auto-discovers them.

---

## 5. Key Configuration Files

### `mobile/apps/user/app.config.ts`
```typescript
// Controls preview features
const isPreview = process.env.AFCON360_PREVIEW_BUILD === "true";
extra: {
  apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://www.pamoja.space",
  allowServerSelection: isPreview,  // ← enables Connection settings page
}
```

### `mobile/apps/user/metro.config.js` (NEW)
```javascript
const { getDefaultConfig } = require("expo/metro-config");
module.exports = (async () => {
  const config = await getDefaultConfig(__dirname);
  config.server = { ...config.server, allowedHosts: ["all"] };
  return config;
})();
```
Allows Metro to accept connections from phone's hotspot IP.

### `mobile/apps/user/app/api/health.py` (NEW endpoint)
```python
@health_bp.route('/server-urls', methods=['GET'])
@limiter.exempt
def server_urls():
    """Returns current laptop IPs for mobile auto-config."""
    ips = _get_local_ips()  # non-loopback IPv4s
    port = current_app.config.get('PORT', 5000)
    return jsonify({
        'api_base_urls': [f"http://{ip}:{port}" for ip in ips],
        'metro_urls': [f"http://{ip}:8081" for ip in ips],
    })
```

### `mobile/apps/user/app/server-settings.tsx` (ENHANCED)
- Auto-fetches `/api/health/server-urls` on load
- Shows **Auto-detected laptop servers** as one-tap buttons
- New **Metro Bundler (Fast Refresh)** section with deep-link connect
- Saves Metro URL to SecureStore (`afcon360.user.metro-url`)

---

## 6. Dev Client Usage

### Install on New Phone
1. Download APK from artifact URL above
2. Enable "Install unknown apps" → open APK
3. App installs as `space.pamoja.afcon360.user.preview`

### First Launch (Wireless)
1. Ensure laptop & phone on **same hotspot** (either device can host)
2. Start Metro: `npx expo start --dev-client --host lan --port 8081` (with `AFCON360_PREVIEW_BUILD=true`)
3. Start Flask: `cd afcon360_app && .venv\Scripts\python.exe app.py`
3. Open app → **Account → Connection settings (preview)**
4. Tap detected API URL (e.g., `http://192.168.100.28:5000`) → "Test and save"
5. Tap detected Metro URL (e.g., `http://192.168.100.28:8081`) → "Save & Connect to Metro"
6. App reloads with wireless Fast Refresh — **no USB needed**

### USB Fallback (if hotspot fails)
```bash
adb reverse tcp:8081 tcp:8081
# In app: use http://127.0.0.1:8081 for Metro
# Flask still needs hotspot IP (or another reverse on 5000)
```

---

## 6. Current State (as of handover)

| Component | Status |
|-----------|--------|
| Dev client installed | ✅ v10 on test device |
| Metro (LAN) | ✅ Running on `192.168.100.28:8081` |
| Flask API | ✅ Running on `192.168.100.28:5000` |
| Fast Refresh | ✅ Verified (magenta→muted footer live) |
| Server selection page | ✅ Auto-detects IPs, one-tap connect |
| Metro deep-link connect | ✅ Opens dev client via `afcon360-preview://expo-development-client/?url=...` |
| Dynamic IP handling | ✅ `/api/health/server-urls` returns current IPs |
| TypeCheck | ✅ Clean |
| Expo export | ✅ Clean (1607 modules) |

---

## 7. Critical Commands Cheatsheet

### Metro
```bash
# Start (LAN, wireless Fast Refresh)
$env:AFCON360_PREVIEW_BUILD="true"; $env:AFCON360_RELEASE_BUILD="false"
npx expo start --dev-client --host lan --port 8081

# Start (localhost, USB only)
$env:AFCON360_PREVIEW_BUILD="true"
npx expo start --dev-client --localhost --port 8081

# Kill stuck Metro
Get-Process -Name "node" | Where-Object {$_.CommandLine -like "*expo*"} | Stop-Process -Force
```

### Flask
```bash
cd C:\Users\OBED\Desktop\afcon360_app
.\.venv\Scripts\python.exe app.py
# Logs show bound IPs (e.g., 192.168.100.28:5000)
```

### ADB
```bash
# USB reverse (Metro)
adb reverse tcp:8081 tcp:8081

# List devices
adb devices

# Install APK
adb install -r path\to\afcon360-dev-client.apk

# Deep-link launch
adb shell am start -a android.intent.action.VIEW -d "afcon360-preview://expo-development-client/?url=http%3A%2F%2F127.0.0.1%3A8081"
```

### EAS
```bash
# Build
$env:AFCON360_USER_EAS_PROJECT_ID="20708e30-4640-4b88-9615-38412f47e811"
npx eas-cli build --profile development --platform android --non-interactive

# Download artifact
npx eas-cli build:download <BUILD_ID> --output afcon360.apk

# OTA Update (wireless, no Metro)
npx eas-cli update --branch preview --message "Hotfix"
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Connection settings unavailable" | `SERVER_SELECTION_ENABLED=false` | Metro started without `AFCON360_PREVIEW_BUILD=true` |
| Metro status times out on LAN IP | Windows Firewall blocking 8081 on Public profile | Run as Admin: `New-NetFirewallRule -DisplayName "Expo Metro 8081" -Direction Inbound -LocalPort 8081 -Protocol TCP -Action Allow -Profile Any` |
| Phone can't reach Flask | Not on same hotspot / wrong IP | Check `/api/health/server-urls` for current IPs; ensure both on same network |
| Fast Refresh not working | Metro not running / USB reverse missing | Verify Metro status at `http://<ip>:8081/status`; run `adb reverse tcp:8081 tcp:8081` |
| White screen on launch | Metro restarted, bundle downloading | Wait 3–5s; subsequent launches instant |
| Dev menu gear flashing | Normal dev-client behavior | Ignore; or build `preview` profile for clean binary |

---

## 9. Files Modified in This Session

### Core Changes (committed in `10d858ba`)
- `mobile/apps/user/src/components/events/TicketPurchase.tsx` — fixed duplicate tails, authClient, registration_reference logic
- `mobile/apps/user/src/components/ride/MapView.tsx` — WebViewCompat cast
- `mobile/apps/user/src/components/ride/{RideChoose,RideWhere,RideConfirm,RideScreen}.tsx` — imports, distanceKm prop
- `mobile/apps/user/src/components/wallet/{WalletDeposit,WalletWithdraw,WalletScreen,WalletUI}.tsx` — imports, prop types
- `mobile/apps/user/src/components/wallet/types.ts` — re-exports core status types
- `mobile/apps/user/src/components/ride/utils.ts` — re-exports TTL constants
- `mobile/apps/user/src/theme/tokens.ts` — added `greenSoft: '#E8F4EC'`
- `mobile/apps/user/src/components/ServiceGrid.tsx` — passes `serviceKey`
- `mobile/apps/user/app/(service)/events.tsx` — `walletAccount ?? undefined`
- Import path fixes across `events/`, `maps/`, `ride/`, `wallet/`

### New / Enhanced (uncommitted, working tree)
- `mobile/apps/user/metro.config.js` — `allowedHosts: ["all"]` for LAN Metro
- `mobile/apps/user/app/api/health.py` — added `/server-urls` endpoint with dynamic IP detection
- `mobile/apps/user/app/server-settings.tsx` — auto-fetch server URLs, one-tap buttons, Metro Bundler section with deep-link connect
- `mobile/apps/user/app.config.ts` — unchanged (already correct)

---

## 10. Next Steps / Follow-ups

1. **Firewall Rule** — Run the Admin PowerShell command once to allow Metro on Public networks permanently.
2. **OTA Channel** — Consider `user-development` channel for internal testers (see `eas.json` dev-apk profile).
3. **Shared UI HMR** — `packages/ui` edits don't hot-reload; restart Metro after shared changes.
4. **Production Build** — When ready, `eas build --profile production` strips dev client, embeds bundle, removes gear.

---

## 11. Contact / Context

- **Repo:** `C:\Users\OBED\Desktop\afcon360-user-dev` (branch `feat/user-offline-first-foundation-20261117`)
- **Main AFCON360 repo:** `C:\Users\OBED\Desktop\afcon360_app`
- **EAS Account:** `twikirizeo` / Project `afcon360-user`
- **Test Device:** `R92XC0H6Q5N` (Galaxy A05, Android 14)

---

## 12. TypeScript/Compile Error Policy (Critical)

**TypeScript/compile errors have been a persistent headache.** 

**MANDATORY RULE:** Any TypeScript addition, modification, or new file **MUST pass `typecheck` and `expo export` locally before committing or pushing to OTA.**

```bash
# Run these TWO commands and confirm BOTH pass:
corepack pnpm --filter @afcon360/user-app run typecheck
corepack pnpm --filter @afcon360/user-app exec expo export --platform android --output-dir "$env:TEMP\opencode\expo-export-check"
```

**No exceptions.** If either fails, fix it locally. Do not push broken code to OTA — it breaks the dev client for all testers and wastes hours of debugging.

This applies to:
- New components/screens
- Modified types/interfaces  
- Import path changes
- New dependencies
- Any `.ts`/`.tsx` changes

---

**This document + the repo state = everything needed to continue immediately.**