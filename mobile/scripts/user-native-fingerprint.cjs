#!/usr/bin/env node
"use strict";

/**
 * Print the native Android runtime fingerprint used as the reusable APK key.
 *
 * Run from mobile/apps/user after workspace dependencies are installed:
 *   node ../../scripts/user-native-fingerprint.cjs
 *
 * Resolve @expo/fingerprint from the User app's own dependency graph so the
 * fingerprint implementation matches this project's installed Expo SDK.
 * fingerprint.config.js preserves the balanced native checks while excluding
 * OTA-only Expo "extra" runtime values.
 */
const path = require("node:path");
const { createRequire } = require("node:module");

async function main() {
  const appRequire = createRequire(path.join(process.cwd(), "package.json"));
  const expoEntry = appRequire.resolve("expo");
  const expoRequire = createRequire(expoEntry);
  const fingerprintEntry = expoRequire.resolve("@expo/fingerprint");
  const Fingerprint = expoRequire(fingerprintEntry);

  if (typeof Fingerprint.createProjectHashAsync !== "function") {
    throw new Error(
      "The installed Expo SDK does not expose createProjectHashAsync from @expo/fingerprint."
    );
  }

  const fingerprintConfig = appRequire("./fingerprint.config.js");
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
