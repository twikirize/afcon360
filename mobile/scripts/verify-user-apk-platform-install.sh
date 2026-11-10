#!/usr/bin/env bash
set -euo pipefail

EXPECTED_API="${1:?Expected Android API level is required}"
APK="${2:?APK path is required}"
SHA_FILE="${3:?APK SHA-256 file path is required}"
EVIDENCE_DIR="${4:?Evidence output directory is required}"
PACKAGE="space.pamoja.afcon360.user.preview"

mkdir -p "$EVIDENCE_DIR"
test -s "$APK"
test -s "$SHA_FILE"

EXPECTED_SHA="$(awk 'NR == 1 { print $1 }' "$SHA_FILE")"
ACTUAL_SHA="$(sha256sum "$APK" | awk '{ print $1 }')"
if [[ -z "$EXPECTED_SHA" || "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  echo "ERROR: APK checksum does not match workflow evidence." >&2
  exit 1
fi

API_LEVEL="$(adb shell getprop ro.build.version.sdk | tr -d '\r')"
ANDROID_RELEASE="$(adb shell getprop ro.build.version.release | tr -d '\r')"
echo "Emulator Android release=$ANDROID_RELEASE API=$API_LEVEL"
if [[ "$API_LEVEL" != "$EXPECTED_API" ]]; then
  echo "ERROR: Expected API $EXPECTED_API but emulator reports $API_LEVEL." >&2
  exit 1
fi

adb get-state
adb install --no-streaming "$APK" | tee "$EVIDENCE_DIR/adb-install.txt"
adb shell pm path "$PACKAGE" | tee "$EVIDENCE_DIR/package-path.txt"
adb shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1 | tee "$EVIDENCE_DIR/launch.txt"
sleep 8
adb shell pidof "$PACKAGE" | tee "$EVIDENCE_DIR/process-id.txt"
adb logcat -d -t 3000 > "$EVIDENCE_DIR/logcat.txt"

echo "PASS: AFCON360 User APK installed and launched on Android $ANDROID_RELEASE (API $API_LEVEL)."
