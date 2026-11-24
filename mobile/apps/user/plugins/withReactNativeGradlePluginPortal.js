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
      // Resolve React Native first. With pnpm, its transitive Gradle plugin
      // is linked beside the React Native package inside that package's
      // virtual-store node_modules, which is not guaranteed to be discoverable
      // by scanning only the workspace-level .pnpm directory.
      const candidateRoots = new Set();
      const addCandidate = (candidate) => {
        if (!candidate) return;
        candidateRoots.add(path.resolve(candidate));
      };

      let reactNativeRoot = null;
      try {
        const reactNativeEntry = require.resolve("react-native", {
          paths: [modConfig.modRequest.projectRoot, mobileRoot],
        });
        let current = path.dirname(reactNativeEntry);
        while (true) {
          const manifestPath = path.join(current, "package.json");
          if (fs.existsSync(manifestPath)) {
            try {
              const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
              if (manifest.name === "react-native") {
                reactNativeRoot = fs.realpathSync(current);
                break;
              }
            } catch {
              // Continue toward the package root.
            }
          }
          const parent = path.dirname(current);
          if (parent === current) break;
          current = parent;
        }
      } catch {
        // Fall through to workspace pnpm-store discovery with useful diagnostics.
      }

      if (reactNativeRoot) {
        const rnNodeModules = path.dirname(reactNativeRoot);
        addCandidate(path.join(rnNodeModules, "@react-native", "gradle-plugin"));
        addCandidate(path.join(reactNativeRoot, "node_modules", "@react-native", "gradle-plugin"));
      }
      addCandidate(path.join(mobileRoot, "node_modules", "@react-native", "gradle-plugin"));

      const pnpmStore = path.join(mobileRoot, "node_modules", ".pnpm");
      const candidates = fs.existsSync(pnpmStore)
        ? fs.readdirSync(pnpmStore)
            .filter((entry) => entry.startsWith("@react-native+gradle-plugin@"))
            .sort()
        : [];
      for (const entry of candidates) {
        addCandidate(path.join(
          pnpmStore,
          entry,
          "node_modules",
          "@react-native",
          "gradle-plugin"
        ));
      }

      const settingsFiles = Array.from(candidateRoots)
        .filter((packageRoot) => {
          const manifestPath = path.join(packageRoot, "package.json");
          if (!fs.existsSync(manifestPath)) return false;
          try {
            const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
            return manifest.name === "@react-native/gradle-plugin";
          } catch {
            return false;
          }
        })
        .map((packageRoot) => path.join(packageRoot, "settings.gradle.kts"))
        .filter((file) => fs.existsSync(file));
      if (settingsFiles.length === 0) {
        throw new Error(
          "AFCON360 could not find React Native Gradle plugin settings.gradle.kts. " +
          "React Native package root: " + (reactNativeRoot || "not resolved") +
          "; checked " + candidateRoots.size + " package locations."
        );
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
