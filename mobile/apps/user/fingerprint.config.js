/** @type {import("@expo/fingerprint").Config} */
module.exports = {
  // Use Expo's balanced native checks, plus the OTA-only runtime "extra" skip.
  // Keep ExpoConfigVersions enabled: runtimeVersion uses appVersion, so changing
  // app version must invalidate the APK to avoid an incompatible OTA runtime.
  // Balanced mask 57859 + ExpoConfigExtraSection 4096 = 61955;
  // subtract ExpoConfigVersions (1) => 61954.
  preset: "balanced",
  sourceSkips: 61954,
  // Keep the policy itself observable in the generated fingerprint.
  extraSources: [{ type: "file", filePath: "fingerprint.config.js" }]
};
