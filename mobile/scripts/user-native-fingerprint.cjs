#!/usr/bin/env node
"use strict";

/**
 * Print the native Android runtime fingerprint used as the reusable APK key.
 *
 * Run from mobile/apps/user after workspace dependencies are installed:
 *   node ../../scripts/user-native-fingerprint.cjs
 *
 * Resolve @expo/fingerprint through the installed Expo package, pinned by this
 * app's SDK. createRequire is rooted at the User app package because this
 * helper lives under mobile/scripts (outside the app's node_modules scope).
 *
 * fingerprint.config.js uses Expo's balanced native preset and skips only
 * ExpoConfigExtraSection: API origin and preview server-selection values are
 * runtime manifest extras, not native binary inputs.
 */
const path = require("node:path");
const { createRequire } = require("node:module");

async function main() {
  const appRequire = createRequire(path.join(process.cwd(), "package.json"));
  const expoEntry = appRequire.resolve("expo");
  const expoRequire = createRequire(expoEntry);
  const Fingerprint = expoRequire("@expo/fingerprint");

  if (typeof Fingerprint.createProjectHashAsync !== "function") {
    throw new Error(
      "The @expo/fingerprint package resolved from this Expo SDK does not expose createProjectHashAsync."
    );
  }

  // Expo Fingerprint automatically loads fingerprint.config.js from the
  // project root and normalizes named SourceSkips into its SDK enum bitmask.
  // Do not pass the raw config object again as runtime options: that would
  // override the normalized values and produce a different fingerprint.
  const hash = await Fingerprint.createProjectHashAsync(process.cwd(), {
    platforms: ["android"],
    silent: true
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
