# User App Local Snapshot Reconciliation

**Review date:** 2026-11-21  
**Repository:** `twikirize/afcon360`  
**Reconciliation branch:** `reconcile/user-local-files-20261121`  
**Snapshot commit:** `d82dfc2b2fbe00ba7b1bb654db910f66cda62e42`  
**Snapshot parent:** `dc841f26c6ed35dc3d76970f5a37bec9d7f2d41d` (`feat/user-offline-first-foundation-20261117`)

## 1. Snapshot status

The laptop's untracked work was committed and pushed as one isolated snapshot: **39 files, 2,288 insertions**. The push succeeded and the working tree was clean at the end of the user's command output.

The snapshot commit is intentionally retained as the recovery point for every file captured. This review does not merge anything into the native User App base, the offline-first branch, or repository `main`.

The snapshot includes no `local.properties`, Android debug keystore, `.pem`, `.jks`, `.p12`, `.pfx`, `.key`, `.p8`, `.env`, or `google-services.json` files in its committed file list. The Android Gradle files refer to `app/debug.keystore`, but that keystore itself was not committed.

## 2. Findings and dispositions

### A. Android native project: preserve in snapshot; do not promote as the active EAS/CNG project

Captured paths are under `mobile/apps/user/android/` (Gradle project, wrapper, app Gradle file, Android manifests, Kotlin entry points, resources and Gradle properties).

**Evidence of mismatch with the current Expo configuration:**

- `mobile/apps/user/app.config.ts` dynamically sets the app package to `space.pamoja.afcon360.user.preview.dev` for the development-client profile and uses the scheme `afcon360-preview-dev`.
- The captured `android/app/build.gradle` hard-codes `applicationId 'space.pamoja.afcon360.user'`.
- The captured main manifest declares the URI schemes `afcon360` and `exp+afcon360-user`, not the current dynamic preview-development scheme.
- The captured main manifest sets `expo.modules.updates.ENABLED` to `false`, while current Expo app configuration installs `expo-updates` and configures an EAS update URL, channel and ON_LOAD checks.
- The captured Gradle release build signs with the debug signing configuration.
- `gradle.properties` contains unverified local build workarounds: disables Fabric/new architecture, restricts native architectures to `arm64-v8a`, and sets CMake/Gradle tuning.

This mismatch is operationally important. Expo's CNG documentation says that when an `android/` directory is present, EAS Build skips Prebuild to avoid overwriting native changes. Therefore, carrying this directory into the active offline-first branch would make EAS build from this captured native project rather than regenerate it from the current dynamic app configuration. See [Expo CNG documentation](https://docs.expo.dev/workflow/continuous-native-generation/).

**Disposition:** keep the entire captured Android tree recoverable in this snapshot commit; do not merge it into the active offline-first branch as-is. Before any native configuration from it is adopted, identify which settings are genuinely required and express those through `app.config.ts` or config plugins where possible, then regenerate and verify the native project. The Kotlin `MainActivity` and `MainApplication` appear to be standard Expo/RN entry-point boilerplate; no AFCON360-specific native business logic was identified in them.

The generated folder's own `.gitignore` excludes Gradle caches, CMake output, build output and local SDK settings; those ignored outputs were not part of the snapshot.

### B. Added screen prototypes: preserve for reference; do not wire into navigation

| Captured file | Finding | Disposition |
|---|---|---|
| `mobile/apps/user/src/screens/HomeScreen.tsx` | A second home-screen implementation. The actual route is `app/(tabs)/index.tsx`, which already loads and refreshes the offline-cached home feed through `userOfflineRepository`, handles offline state, and uses the current shared home components. The new file is not the route used by Expo Router. | Reference only; do not replace or wire over the current offline-first home route. |
| `mobile/apps/user/src/components/ride/RideBookingScreen.tsx` | A standalone booking mock-up. It uses a hard-coded greeting name, a decorative map area and placeholder alerts; its Confirm Ride handler only displays an alert rather than running the quote, confirmation, request, matching and booking lifecycle. | Reference only; do not wire into the app. |

The existing ride route is `app/(service)/ride.tsx`, which exports the existing `src/components/ride/RideScreen.tsx`. That flow already contains the request-first stages, location search/map handling, fare quotes, payment method selection and request submission. The new mock-up is not a missing ride module.

### C. Windows development utilities

| Captured file | Finding | Disposition |
|---|---|---|
| `create-scheduled-task.ps1` | One-time Windows Task Scheduler setup. It uses machine-specific absolute paths and unregisters an existing task with the same name before registering a replacement. | One-time setup script; do not run or promote into routine developer tooling. Retain only in the snapshot history unless a safe, parameterized setup tool is later justified. |
| `debug-ip.ps1` | Diagnostic IP enumeration and preferred-address probe. | One-off diagnostic; no application dependency identified. |
| `test-ip.ps1` | Another diagnostic IP enumeration script, overlapping with `debug-ip.ps1`. | Duplicate/one-off diagnostic; no application dependency identified. |
| `mobile/apps/user/launch-phone.ps1` | Potentially useful ADB deep-link helper, but hard-codes the old `.preview` package and `afcon360-preview` scheme, plus a machine-specific ADB path. Current dev-client identity is `.preview.dev` with `afcon360-preview-dev`. | Keep the idea; rewrite before reuse. |
| `mobile/apps/user/start-wifi.ps1` | Useful Metro-over-LAN concept, but recognizes only a narrow set of hotspot address ranges. | Keep the idea; make IP detection generic and align its launch instructions with the development-client setup. |
| `start-afcon360.ps1` | Combines Flask, Metro, firewall setup and phone launch. It hard-codes both repository paths, uses the old preview package/scheme, and attempts process detection through `Get-Process` objects' `CommandLine` property. That process-detection approach needs correction. It can also elevate PowerShell to create a firewall rule. | Do not rely on as-is; archive as a historical experiment and replace only after a safe, parameterized local workflow is designed. |
| `start-afcon360.bat` | Thin wrapper that starts the above PowerShell launcher. | Keep only if the launcher is rewritten; otherwise no independent value. |

No Python/Flask source changes were part of this snapshot.

## 3. Recommended reconciliation plan

1. Keep `d82dfc2b` as the immutable recovery snapshot.
2. Do not merge the captured Android directory into the offline-first branch. Keep CNG as the source of truth unless a reviewed native customization is deliberately ported into Expo config/plugins.
3. Do not add either prototype screen to the active navigation. The current offline-aware home route and request-first ride route already exist.
4. Retire the one-off IP diagnostics and scheduled-task installer from the active project tree; their complete contents remain recoverable from the snapshot commit.
5. Rewrite the useful Metro/ADB helpers against the actual development-client identity and a portable Android SDK lookup before placing them in a maintained developer-tools location.
6. Only after that cleanup should selected, proven changes be transferred from this reconciliation branch to the offline-first working branch.

## 4. Changes made by this review

This document records the evidence and recommended dispositions. No files from the snapshot have been deleted, moved, modified, or merged by this review. The original snapshot commit remains intact.
