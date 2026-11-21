# User App Local Snapshot Cleanup

**Repository:** `twikirize/afcon360`  
**Branch:** `reconcile/user-local-files-20261121`  
**Recovery snapshot:** `d82dfc2b2fbe00ba7b1bb654db910f66cda62e42`  
**Cleanup parent:** `cd6159cddfedb72a3573827d5a2f41bc6fbc649a`

## Applied corrections

The full laptop snapshot remains in Git history as the recovery point. The following corrections apply only to this branch's active tree:

1. Removed the captured `mobile/apps/user/android/` directory. The User App uses Expo Continuous Native Generation (CNG), so EAS should generate native Android files from `app.config.ts` and config plugins. The captured Android project hard-coded the old package and URI schemes and disabled Expo Updates; it did not match the current development-client identity.
2. Added explicit root `.gitignore` and `.easignore` entries for `mobile/apps/user/android/` and `mobile/apps/user/ios/` so generated native projects are not accidentally committed or included in the EAS archive.
3. Removed the un-routed `HomeScreen.tsx` and `RideBookingScreen.tsx` prototypes. The active home route remains `app/(tabs)/index.tsx` with offline repository/cache integration. The active ride route remains `app/(service)/ride.tsx` and the existing multi-stage `RideScreen`.
4. Removed the one-time scheduled-task installer, temporary IP diagnostics, and old machine-specific launcher wrappers from the active tree. Their contents remain recoverable from the snapshot commit.
5. Added maintained Windows development helpers in `mobile/scripts/windows/`:
   - `start-user-metro.ps1`: resolves the workspace relative to its own location; sets the configured development-client identity/channel; supports a custom API base URL; refuses to reuse an occupied Metro port; starts Metro only and makes no firewall or native-build changes.
   - `launch-user-dev-client.ps1`: discovers ADB without a hard-coded SDK path; selects an authorized connected device; verifies the expected `.preview.dev` package is installed; opens the `afcon360-preview-dev` Metro deep link.
   - `README.md`: documents usage and the JS/TS versus native rebuild boundary.

## Scope and safety

- All changes are confined to this reconciliation branch.
- The native User App base and offline-first working branch are unchanged.
- The original complete snapshot is the parent commit in Git history.
- No production server, database, EAS credential, signing credential, or release channel was changed.
- No APK was built or published by this cleanup.

## Verification status

The GitHub source tree and Expo configuration were statically reviewed. The PowerShell helpers have **not** been executed on the user's Windows laptop. Metro startup, ADB device launch, Expo Prebuild, TypeScript checks, and Android APK build still need verification before any selected result is transferred to the offline-first branch.
