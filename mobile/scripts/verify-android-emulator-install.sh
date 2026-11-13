#!/usr/bin/env bash
# Keep install/launch verification in one Bash process. The emulator action may
# otherwise execute script lines in separate shells and lose local state.
set -Eeuo pipefail

APP="${1:?Usage: verify-android-emulator-install.sh <app> <package> <api-level>}"
EXPECTED_PACKAGE="${2:?Expected Android package ID is required}"
API_LEVEL="${3:?Android API level is required}"
WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"
APK="$WORKSPACE/release/$APP-preview.apk"
UI_DUMP_PATH="/sdcard/afcon360-ui-hierarchy.xml"
UI_DUMP_LOG="/tmp/afcon360-uiautomator-dump.log"

case "$APP" in
  user)
    EXPECTED_APP_LABEL="AFCON360 User"
    EXPECTED_PRIMARY_ACTION="Sign in securely"
    ;;
  driver)
    EXPECTED_APP_LABEL="AFCON360 Driver"
    EXPECTED_PRIMARY_ACTION="Sign in to Driver"
    ;;
  *)
    echo "::error::Unknown AFCON360 app '$APP'; expected user or driver."
    exit 2
    ;;
esac

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

# A live Android process alone does not prove React Native rendered the app.
# Inspect the accessibility/UI hierarchy and require both the correct app
# identity and its native sign-in action. No credentials or backend writes are
# involved in this smoke check.
#
# Fresh Pixel emulator images can occasionally show the system-level
# "Pixel Launcher isn't responding" dialog during first boot. This is not an
# AFCON360 app failure. Detect only that exact system dialog and press Wait,
# then continue requiring the real AFCON360 sign-in UI.
dismiss_known_emulator_system_dialog() {
  adb shell uiautomator dump "$UI_DUMP_PATH" >/dev/null 2>&1 || return 0
  local hierarchy button_id button_label
  hierarchy="$(adb shell cat "$UI_DUMP_PATH" 2>/dev/null | tr -d '\r' || true)"

  # Android 24's Google APIs image can display a crash dialog for its bundled
  # Messenger app during first boot. This is not AFCON360. Close only a
  # background-system-app dialog; never dismiss an AFCON360 app crash.
  if [[ "$hierarchy" == *"Pixel Launcher isn't responding"* ]]; then
    button_id="android:id/aerr_wait"
    button_label="Wait"
  elif [[ "$hierarchy" == *" has stopped"* ]] &&
       [[ "$hierarchy" != *"$EXPECTED_APP_LABEL has stopped"* ]]; then
    button_id="android:id/aerr_close"
    button_label="Close app"
  else
    return 0
  fi

  local coords
  coords="$(printf '%s' "$hierarchy" | BUTTON_ID="$button_id" BUTTON_LABEL="$button_label" python3 -c '
import os
import re
import sys
import xml.etree.ElementTree as ET
try:
    root = ET.fromstring(sys.stdin.read())
except ET.ParseError:
    raise SystemExit(1)
wanted_id = os.environ["BUTTON_ID"]
wanted_text = os.environ["BUTTON_LABEL"]
for node in root.iter("node"):
    if node.attrib.get("resource-id") == wanted_id or node.attrib.get("text") == wanted_text:
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds", ""))
        if match:
            left, top, right, bottom = map(int, match.groups())
            print((left + right) // 2, (top + bottom) // 2)
            raise SystemExit(0)
raise SystemExit(1)
' 2>/dev/null)" || true

  if [[ -n "$coords" ]]; then
    read -r x y <<< "$coords"
    echo "::warning::Emulator displayed an unrelated system dialog; applying its safe system action and rechecking AFCON360."
    adb shell input tap "$x" "$y"
    sleep 3
  fi
}
screen_rendered=0
for attempt in {1..20}; do
  dismiss_known_emulator_system_dialog
  if adb shell uiautomator dump "$UI_DUMP_PATH" >"$UI_DUMP_LOG" 2>&1; then
    screen_xml="$(adb shell cat "$UI_DUMP_PATH" 2>/dev/null | tr -d '\r\n' || true)"
    if [[ "$screen_xml" == *"$EXPECTED_APP_LABEL"* ]] &&
       [[ "$screen_xml" == *"$EXPECTED_PRIMARY_ACTION"* ]]; then
      screen_rendered=1
      break
    fi
  fi
  sleep 2
done

if [[ "$screen_rendered" -ne 1 ]]; then
  echo "::error::$APP process stayed alive but its expected native sign-in screen was not confirmed on Android API $API_LEVEL."
  echo "::group::Rendered-screen diagnostics"
  cat "$UI_DUMP_LOG" 2>/dev/null || true
  adb shell uiautomator dump "$UI_DUMP_PATH" >/dev/null 2>&1 || true
  adb shell cat "$UI_DUMP_PATH" 2>/dev/null || true
  adb logcat -d -t 2500 | tail -n 500 || true
  adb shell dumpsys activity activities || true
  echo "::endgroup::"
  exit 1
fi

echo "PASS: $APP installed, stayed running and rendered '$EXPECTED_APP_LABEL' with '$EXPECTED_PRIMARY_ACTION' on Android API $API_LEVEL."
adb shell getprop ro.build.version.release
adb shell getprop ro.build.version.sdk
