/** @type {import("@expo/fingerprint").Config} */
module.exports = {
  // Use Expo's balanced native checks, plus the OTA-only runtime "extra" skip.
  // Balanced mask: 57859; ExpoConfigExtraSection: 4096; combined: 61955.
  // This leaves plugins, app identity/scheme, native dependencies and native
  // project configuration in the fingerprint.
  preset: "balanced",
  sourceSkips: 61955,
  // Keep the policy itself observable in the generated fingerprint.
  extraSources: [{ type: "file", filePath: "fingerprint.config.js" }]
};
