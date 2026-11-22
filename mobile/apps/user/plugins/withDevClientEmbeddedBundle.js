"use strict";

const { withAppBuildGradle } = require("expo/config-plugins");

/**
 * A React Native debuggable variant normally omits its JavaScript bundle and
 * requires Metro. AFCON360's internal development APK needs both modes:
 *
 * - Metro remains the preferred source for live development/Fast Refresh.
 * - The APK also carries a build-time JavaScript bundle so the development
 *   client has an embedded fallback when the laptop is unavailable.
 *
 * React Native Gradle Plugin skips bundle generation for variants listed in
 * debuggableVariants. Removing "debug" from that list enables the bundle task
 * for the EAS development APK without turning off the development client.
 */
module.exports = function withDevClientEmbeddedBundle(config, options = {}) {
  if (options.enabled !== true) return config;

  return withAppBuildGradle(config, (modConfig) => {
    const contents = modConfig.modResults.contents;
    const reactOpen = /\breact\s*\{/.exec(contents);
    if (!reactOpen) {
      throw new Error(
        "AFCON360 could not find the React Native react { } block in android/app/build.gradle."
      );
    }

    const openBrace = contents.indexOf("{", reactOpen.index);
    const closeLine = contents.indexOf("\n}", openBrace);
    if (closeLine < 0) {
      throw new Error(
        "AFCON360 could not find the end of the React Native react { } Gradle block."
      );
    }

    const block = contents.slice(openBrace + 1, closeLine);
    const setting = /^([ \t]*)(?:\/\/\s*)?debuggableVariants\s*=.*$/m.exec(block);
    let updatedBlock;

    if (setting) {
      const replacement = setting[1] +
        "debuggableVariants = [] // Bundle debug JS while retaining expo-dev-client and Metro.";
      updatedBlock = block.replace(setting[0], replacement);
    } else {
      updatedBlock =
        "\n    debuggableVariants = [] // Bundle debug JS while retaining expo-dev-client and Metro." +
        block;
    }

    if (updatedBlock === block && !/^\s*debuggableVariants\s*=\s*\[\s*\]/m.test(block)) {
      throw new Error("AFCON360 failed to configure the development APK embedded bundle.");
    }

    modConfig.modResults.contents =
      contents.slice(0, openBrace + 1) + updatedBlock + contents.slice(closeLine);

    return modConfig;
  });
};
