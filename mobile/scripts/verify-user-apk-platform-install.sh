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
# Emulator boot completion can precede Package Manager readiness, especially
# on newer Android images. Wait for the service rather than misclassifying a
# transient Binder failure as an APK compatibility failure.
package_manager_ready=false
for attempt in $(seq 1 60); do
  SERVICE_STATUS="$(adb shell service check package 2>&1 || true)"
  PACKAGE_LIST="$(adb shell pm list packages 2>&1 || true)"
  if grep -qi "found" <<< "$SERVICE_STATUS" && grep -q "^package:" <<< "$PACKAGE_LIST"; then
    package_manager_ready=true
    echo "ANDROID_PACKAGE_MANAGER_READY after ${attempt} check(s)."
    break
  fi
  sleep 2
done
if [[ "$package_manager_ready" != "true" ]]; then
  adb shell service list > "$EVIDENCE_DIR/android-services.txt" 2>&1 || true
  adb shell dumpsys -l > "$EVIDENCE_DIR/android-dumpsys-services.txt" 2>&1 || true
  adb logcat -d -t 2000 > "$EVIDENCE_DIR/android-boot-logcat.txt" 2>&1 || true
  echo "::error::ANDROID_TEST_INFRA_FAILURE: Android Package Manager did not become usable within 120 seconds after emulator boot."
  exit 1
fi
adb install --no-streaming "$APK" | tee "$EVIDENCE_DIR/adb-install.txt"
adb shell pm path "$PACKAGE" | tee "$EVIDENCE_DIR/package-path.txt"
adb shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1 | tee "$EVIDENCE_DIR/launch.txt"
sleep 8
adb shell pidof "$PACKAGE" | tee "$EVIDENCE_DIR/process-id.txt"
adb logcat -d -t 3000 > "$EVIDENCE_DIR/logcat.txt"

echo "PASS: AFCON360 User APK installed and launched on Android $ANDROID_RELEASE (API $API_LEVEL)."
