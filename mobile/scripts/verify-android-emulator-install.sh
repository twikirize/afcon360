#!/usr/bin/env bash
# Keep install/launch verification in one Bash process. The emulator action may
# otherwise execute script lines in separate shells and lose local state.
set -Eeuo pipefail

APP="${1:?Usage: verify-android-emulator-install.sh <app> <package> <api-level>}"
EXPECTED_PACKAGE="${2:?Expected Android package ID is required}"
API_LEVEL="${3:?Android API level is required}"
WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"
APK="$WORKSPACE/release/$APP-preview.apk"

echo "Checking $APP APK on Android API $API_LEVEL."
if [[ ! -s "$APK" ]]; then
  echo "::error::Expected APK is missing or empty: $APK"
  find "$WORKSPACE" -maxdepth 5 -type f -name '*.apk' -print || true
  exit 1
fi

ls -lh "$APK"
adb wait-for-device
if ! adb logcat -c >/dev/null 2>&1; then
  echo "::warning::Could not clear emulator log buffer; continuing with install checks."
fi

if ! adb install "$APK"; then
  echo "::error::Android Package Manager rejected $APP on API $API_LEVEL."
  echo "::group::Install diagnostics"
  adb shell pm list packages | grep -F "$EXPECTED_PACKAGE" || true
  adb logcat -d -t 2500 | tail -n 500 || true
  echo "::endgroup::"
  exit 1
fi

if ! adb shell monkey -p "$EXPECTED_PACKAGE" -c android.intent.category.LAUNCHER 1; then
  echo "::error::Android could not launch $APP on API $API_LEVEL."
  adb logcat -d -t 2500 | tail -n 500 || true
  exit 1
fi

started=0
for attempt in {1..12}; do
  if adb shell ps | grep -F "$EXPECTED_PACKAGE" >/dev/null 2>&1; then
    started=1
    break
  fi
  sleep 5
done

if [[ "$started" -ne 1 ]]; then
  echo "::error::$APP installed but did not stay running on API $API_LEVEL."
  echo "::group::Launch diagnostics"
  adb logcat -d -t 2500 | tail -n 500 || true
  adb shell dumpsys activity activities || true
  echo "::endgroup::"
  exit 1
fi

echo "PASS: $APP installed and launched on Android API $API_LEVEL."
adb shell getprop ro.build.version.release
adb shell getprop ro.build.version.sdk
