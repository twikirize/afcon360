const fs = require("node:fs");
const path = require("node:path");
const { withDangerousMod } = require("expo/config-plugins");

function findInstalledPackageRoot(packageName, expectedVersion, startDirectory) {
  const packageSegments = packageName.split("/");
  const virtualStorePrefix = packageName.startsWith("@")
    ? packageName.replace("/", "+")
    : packageName;
  const candidates = [];
  const seen = new Set();
  const add = (candidate) => {
    const resolved = path.resolve(candidate);
    if (!seen.has(resolved)) {
      seen.add(resolved);
      candidates.push(resolved);
    }
  };

  let current = path.resolve(startDirectory);
  while (true) {
    add(path.join(current, "node_modules", ...packageSegments));
    const virtualStore = path.join(current, "node_modules", ".pnpm");
    if (fs.existsSync(virtualStore)) {
      for (const entry of fs.readdirSync(virtualStore)) {
        if (entry.startsWith(virtualStorePrefix + "@")) {
          add(path.join(virtualStore, entry, "node_modules", ...packageSegments));
        }
      }
    }
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }

  const exactVersion = typeof expectedVersion === "string"
    ? expectedVersion.match(/\d+\.\d+\.\d+/)?.[0]
    : null;
  for (const candidate of candidates) {
    const manifestPath = path.join(candidate, "package.json");
    if (!fs.existsSync(manifestPath)) continue;
    try {
      const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
      if (
        manifest.name === packageName &&
        (!exactVersion || manifest.version === exactVersion)
      ) {
        return candidate;
      }
    } catch {
      // Keep checking other valid workspace/package-manager candidates.
    }
  }

  throw new Error(
    "AFCON360 could not locate " + packageName +
    (expectedVersion ? "@" + expectedVersion : "") +
    " from " + startDirectory + "."
  );
}

/**
 * React Native 0.88.1's published Gradle plugin settings already include the
 * Gradle Plugin Portal needed for the Foojay resolver. Verify the installed
 * version selected by React Native rather than assuming one pnpm-store path.
 * If a future upstream version removes the repository, restore it idempotently
 * and fail loudly if the settings structure changes.
 */
module.exports = function withReactNativeGradlePluginPortal(config) {
  return withDangerousMod(config, [
    "android",
    async (modConfig) => {
      const projectRoot = modConfig.modRequest.projectRoot;
      const appManifest = JSON.parse(
        fs.readFileSync(path.join(projectRoot, "package.json"), "utf8")
      );
      const reactNativeRoot = findInstalledPackageRoot(
        "react-native",
        appManifest.dependencies?.["react-native"],
        projectRoot
      );
      const reactNativeManifest = JSON.parse(
        fs.readFileSync(path.join(reactNativeRoot, "package.json"), "utf8")
      );
      const gradlePluginRoot = findInstalledPackageRoot(
        "@react-native/gradle-plugin",
        reactNativeManifest.dependencies?.["@react-native/gradle-plugin"],
        reactNativeRoot
      );
      const settingsFile = path.join(gradlePluginRoot, "settings.gradle.kts");

      if (!fs.existsSync(settingsFile)) {
        throw new Error(
          "AFCON360 could not find settings.gradle.kts in the selected React Native Gradle plugin: " +
          gradlePluginRoot
        );
      }

      const original = fs.readFileSync(settingsFile, "utf8");
      if (original.includes("gradlePluginPortal()")) {
        console.log("AFCON360 React Native Gradle plugin already includes Gradle Plugin Portal.");
        return modConfig;
      }

      const repositoriesBlock = /pluginManagement\s*\{\s*repositories\s*\{/m.exec(original);
      if (!repositoriesBlock) {
        throw new Error(
          "AFCON360 could not find pluginManagement.repositories in the selected React Native Gradle plugin."
        );
      }

      const insertionPoint = repositoriesBlock.index + repositoriesBlock[0].length;
      const updated =
        original.slice(0, insertionPoint) +
        "\n    gradlePluginPortal()" +
        original.slice(insertionPoint);
      fs.writeFileSync(settingsFile, updated, "utf8");
      console.log("AFCON360 restored Gradle Plugin Portal for the React Native Foojay resolver.");
      return modConfig;
    }
  ]);
};
