/** @type {import("@expo/fingerprint").Config} */
module.exports = {
  // Use Expo SDK 58's balanced defaults, plus the OTA-only ExpoConfig extra
  // section. Config sourceSkips replaces (rather than extends) preset defaults,
  // so list every balanced default explicitly.
  preset: "balanced",
  sourceSkips: [
    "ExpoConfigVersions",
    "ExpoConfigRuntimeVersionIfString",
    "PackageJsonAndroidAndIosScriptsIfNotContainRun",
    "EasJson",
    "Easignore",
    "AutolinkingConfigPaths",
    "ExpoConfigExtraSection"
  ],
  // Make a deliberate policy change visible to the native APK cache key.
  extraSources: [{ type: "file", filePath: "fingerprint.config.js" }]
};
