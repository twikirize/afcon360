/** @type {import("expo/fingerprint").Config} */
module.exports = {
  // Hash the native runtime surface, not every JavaScript/TypeScript source file.
  preset: "balanced",
  // API origin and preview server-selection flags live in Expo's JS runtime
  // manifest. They can be delivered by a compatible OTA update and must not
  // cause an Android binary rebuild.
  sourceSkips: ["ExpoConfigExtraSection"],
  // Keep the policy itself observable in the generated fingerprint.
  extraSources: [{ type: "file", filePath: "fingerprint.config.js" }]
};
