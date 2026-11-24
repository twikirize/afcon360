const fs = require("node:fs");
const path = require("node:path");
const { withDangerousMod } = require("expo/config-plugins");

/**
 * React Native 0.88.1's included Gradle plugin build needs the Gradle Plugin
 * Portal to resolve org.gradle.toolchains.foojay-resolver-convention:1.0.0.
 * The upstream included build currently searches Maven Central only.
 *
 * This idempotent config plugin adjusts the dependency's own settings file
 * before the Android Gradle build. It applies to both local E2E prebuilds and
 * EAS preview builds, and fails loudly if the upstream layout changes.
 */
module.exports = function withReactNativeGradlePluginPortal(config) {
  return withDangerousMod(config, [
    "android",
    async (modConfig) => {
      const mobileRoot = path.resolve(modConfig.modRequest.projectRoot, "../..");
      const pnpmStore = path.join(mobileRoot, "node_modules", ".pnpm");
      // The workspace currently uses node-linker=hoisted, so the package may
      // live directly under node_modules. Keep the virtual-store lookup too
      // for standard pnpm isolated layouts.
      const candidates = fs.existsSync(pnpmStore)
        ? fs.readdirSync(pnpmStore)
            .filter((entry) => entry.startsWith("@react-native+gradle-plugin@"))
            .sort()
        : [];
      const directSettingsFile = path.join(
        mobileRoot,
        "node_modules",
        "@react-native",
        "gradle-plugin",
        "settings.gradle.kts"
      );
      const settingsFiles = [
        directSettingsFile,
        ...candidates.map((entry) => path.join(
          pnpmStore,
          entry,
          "node_modules",
          "@react-native",
          "gradle-plugin",
          "settings.gradle.kts"
        ))
      ]
        .filter((file, index, all) => all.indexOf(file) === index)
        .filter((file) => fs.existsSync(file));

      if (settingsFiles.length === 0) {
        throw new Error("AFCON360 could not find React Native Gradle plugin settings.gradle.kts.");
      }

      for (const settingsFile of settingsFiles) {
        const original = fs.readFileSync(settingsFile, "utf8");
        if (original.includes("gradlePluginPortal()")) {
          console.log("AFCON360 Gradle Plugin Portal already configured.");
          continue;
        }

        const repositoriesBlock = /pluginManagement\s*\{\s*repositories\s*\{/m.exec(original);
        if (!repositoriesBlock) {
          throw new Error("AFCON360 could not find pluginManagement.repositories in the React Native Gradle plugin.");
        }

        const insertionPoint = repositoriesBlock.index + repositoriesBlock[0].length;
        const updated =
          original.slice(0, insertionPoint) +
          "\n        gradlePluginPortal()" +
          original.slice(insertionPoint);
        fs.writeFileSync(settingsFile, updated, "utf8");
        console.log("AFCON360 enabled Gradle Plugin Portal for the React Native Foojay resolver.");
      }

      return modConfig;
    }
  ]);
};
