#!/usr/bin/env node
"use strict";

/**
 * Print the native Android runtime fingerprint used as the reusable APK key.
 *
 * Run from mobile/apps/user after workspace dependencies are installed:
 *   node ../../scripts/user-native-fingerprint.cjs
 *
 * The fingerprint includes native dependencies, config plugins and native
 * project/configuration inputs. It intentionally excludes OTA-only JS/TS app
 * source and Expo config "extra" values (API origin/server-selection runtime
 * values). Bump the E2E_APK_RECIPE_VERSION in the workflow when changing the
 * disposable APK build recipe itself (e.g. manifest patch, SDK/build tools,
 * signing mode or Gradle invocation).
 */
const Fingerprint = require("expo/fingerprint");

async function main() {
  if (typeof Fingerprint.createProjectHashAsync !== "function") {
    throw new Error(
      "Expo Fingerprint API is unavailable. Check the installed Expo SDK and workspace dependencies."
    );
  }

  const hash = await Fingerprint.createProjectHashAsync(process.cwd(), {
    platforms: ["android"],
    preset: "balanced"
  });

  if (typeof hash !== "string" || !/^[a-f0-9]{20,}$/i.test(hash)) {
    throw new Error("Expo Fingerprint returned an invalid Android native hash.");
  }

  process.stdout.write(hash + "\n");
}

main().catch((error) => {
  console.error("Unable to calculate AFCON360 User native APK fingerprint:", error);
  process.exitCode = 1;
});
