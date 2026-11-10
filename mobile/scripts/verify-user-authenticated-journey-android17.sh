#!/usr/bin/env bash
set -euo pipefail

API_LEVEL="$(adb shell getprop ro.build.version.sdk | tr -d '\r')"
ANDROID_RELEASE="$(adb shell getprop ro.build.version.release | tr -d '\r')"
echo "Full AFCON360 User journey will run on Android $ANDROID_RELEASE (API $API_LEVEL)."

if [[ "$API_LEVEL" != "37" ]]; then
  echo "ERROR: This is not the Android 17 API 37 emulator." >&2
  exit 1
fi

exec python mobile/scripts/verify-user-authenticated-journey.py
