#!/usr/bin/env node
"use strict";

/**
 * Print the native Android runtime fingerprint used as the reusable APK key.
 *
 * Run from mobile/apps/user after workspace dependencies are installed:
 *   node ../../scripts/user-native-fingerprint.cjs
 *
 * Resolve @expo/fingerprint from the installed Expo package so the fingerprint
 * version matches this app's SDK rather than an unpinned latest CLI download.
 * The project's fingerprint.config.js supplies the balanced native-only
 * policy, excluding OTA-only Expo "extra" runtime values.
 *
 * Bump E2E_APK_RECIPE_VERSION in mobile-workspace.yml when changing the
 * disposable APK build recipe itself (manifest patch, SDK/build tools,
 * signing mode or Gradle invocation).
 */
const path = require("node:path");

async function main() {
  const expoEntry = require.resolve("expo");
  const fingerprintPackage = require.resolve("@expo/fingerprint", {
    paths: [path.dirname(expoEntry)]
  });
  const Fingerprint = require(fingerprintPackage);

  if (typeof Fingerprint.createProjectHashAsync !== "function") {
    throw new Error(
      "The installed Expo SDK does not expose createProjectHashAsync from @expo/fingerprint."
    );
  }

  const fingerprintConfig = require(path.join(process.cwd(), "fingerprint.config.js"));
  const hash = await Fingerprint.createProjectHashAsync(process.cwd(), {
    ...fingerprintConfig,
    platforms: ["android"]
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
