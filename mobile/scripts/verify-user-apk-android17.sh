#!/usr/bin/env bash
set -euo pipefail

APK="mobile-e2e-cache/user-e2e.apk"
PACKAGE="space.pamoja.afcon360.user.preview"
EVIDENCE_DIR="android17-install-evidence"
mkdir -p "$EVIDENCE_DIR"

if [[ ! -s "$APK" ]]; then
  echo "ERROR: Expected cached APK is missing: $APK" >&2
  exit 1
fi

API_LEVEL="$(adb shell getprop ro.build.version.sdk | tr -d '\r')"
ANDROID_RELEASE="$(adb shell getprop ro.build.version.release | tr -d '\r')"
echo "Emulator Android release=$ANDROID_RELEASE API=$API_LEVEL"

if [[ "$API_LEVEL" != "37" ]]; then
  echo "ERROR: Expected Android API 37, emulator reported '$API_LEVEL'." >&2
  exit 1
fi

adb get-state
adb install --no-streaming "$APK" | tee "$EVIDENCE_DIR/adb-install.txt"
adb shell pm path "$PACKAGE" | tee "$EVIDENCE_DIR/package-path.txt"
adb shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1 | tee "$EVIDENCE_DIR/launch.txt"
sleep 8
adb logcat -d -t 3000 > "$EVIDENCE_DIR/logcat.txt"

echo "PASS: exact cached AFCON360 User APK installed and launch intent dispatched on Android $ANDROID_RELEASE (API $API_LEVEL)."
