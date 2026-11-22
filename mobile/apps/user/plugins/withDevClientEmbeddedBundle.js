"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { withAppBuildGradle, withDangerousMod } = require("expo/config-plugins");

/**
 * AFCON360's single development APK uses Metro for active editing, a compatible
 * EAS Update when Metro is unavailable, and its embedded bundle if neither
 * network source can load.
 *
 * React Native Gradle Plugin normally omits JS for debuggable variants.
 * Removing "debug" from debuggableVariants embeds JS without disabling Metro.
 *
 * SDK 58 DevLauncher normally returns to its launcher after failed URL loading.
 * Patch both failed-loader and failed-default-URL paths to try the embedded
 * app first. Exact source guards stop the native build if Expo changes these
 * code paths and the patch needs review.
 */
module.exports = function withDevClientEmbeddedBundle(config, options = {}) {
  if (options.enabled !== true) return config;

  config = withAppBuildGradle(config, (modConfig) => {
    const contents = modConfig.modResults.contents;
    const reactOpen = /\breact\s*\{/.exec(contents);
    if (!reactOpen) {
      throw new Error("AFCON360 could not find React Native's react { } Gradle block.");
    }

    const openBrace = contents.indexOf("{", reactOpen.index);
    const closeLine = contents.indexOf("\n}", openBrace);
    if (closeLine < 0) {
      throw new Error("AFCON360 could not find the end of the React Native Gradle block.");
    }

    const block = contents.slice(openBrace + 1, closeLine);
    const setting = /^([ \t]*)(?:\/\/\s*)?debuggableVariants\s*=.*$/m.exec(block);
    let updatedBlock;

    if (setting) {
      updatedBlock = block.replace(
        setting[0],
        setting[1] + "debuggableVariants = [] // Keep Metro and also ship an embedded JS bundle."
      );
    } else {
      updatedBlock =
        "\n    debuggableVariants = [] // Keep Metro and also ship an embedded JS bundle." +
        block;
    }

    if (updatedBlock === block && !/^\s*debuggableVariants\s*=\s*\[\s*\]/m.test(block)) {
      throw new Error("AFCON360 failed to enable the embedded development bundle.");
    }

    modConfig.modResults.contents =
      contents.slice(0, openBrace + 1) + updatedBlock + contents.slice(closeLine);
    return modConfig;
  });

  return withDangerousMod(config, [
    "android",
    async (modConfig) => {
      const devClientEntry = require.resolve("expo-dev-client");
      const launcherEntry = require.resolve("expo-dev-launcher", {
        paths: [path.dirname(devClientEntry)],
      });
      const launcherRoot = path.resolve(path.dirname(launcherEntry), "..");
      const controllerPath = path.join(
        launcherRoot,
        "android",
        "src",
        "debug",
        "java",
        "expo",
        "modules",
        "devlauncher",
        "DevLauncherController.kt",
      );

      if (!fs.existsSync(controllerPath)) {
        throw new Error(
          "AFCON360 could not locate the installed Expo DevLauncherController.kt. " +
          "Review the SDK-specific fallback patch before building."
        );
      }

      const source = fs.readFileSync(controllerPath, "utf8");
      const originalDefaultFallback = [
        "      } catch (_: Throwable) {",
        "        navigateToLauncher()",
        "      }",
        "    }",
        "  }",
        "",
        "  override fun handleIntent",
      ].join("\n");
      const patchedDefaultFallback = [
        "      } catch (_: Throwable) {",
        "        try {",
        "          if (hasEmbeddedBundle()) {",
        "            loadEmbeddedBundle(activityToBeInvalidated)",
        "          } else {",
        "            navigateToLauncher()",
        "          }",
        "        } catch (_: Throwable) {",
        "          navigateToLauncher()",
        "        }",
        "      }",
        "    }",
        "  }",
        "",
        "  override fun handleIntent",
      ].join("\n");

      const originalLoaderFailure = [
        "      } else {",
        "        // The app couldn't be loaded. For now, we just return to the launcher.",
        "        mode = Mode.LAUNCHER",
        "        manifest = null",
        "        manifestURL = null",
        "      }",
      ].join("\n");
      const patchedLoaderFailure = [
        "      } else {",
        "        // Neither Metro nor the EAS update loader initialized; try the bundled app.",
        "        synchronized(this) {",
        "          appIsLoading = false",
        "          _isLoadingToBundler.value = false",
        "        }",
        "        if (hasEmbeddedBundle()) {",
        "          loadEmbeddedBundle(mainActivity)",
        "        } else {",
        "          mode = Mode.LAUNCHER",
        "          manifest = null",
        "          manifestURL = null",
        "          navigateToLauncher()",
        "        }",
        "      }",
      ].join("\n");

      const hasDefaultFallback = source.includes(patchedDefaultFallback);
      const hasLoaderFallback = source.includes(patchedLoaderFailure);
      if (hasDefaultFallback && hasLoaderFallback) {
        console.log("AFCON360 automatic embedded-bundle fallbacks are already patched.");
        return modConfig;
      }
      if (hasDefaultFallback || hasLoaderFallback) {
        throw new Error(
          "AFCON360 found a partially patched Expo DevLauncher. Refusing a mixed startup configuration."
        );
      }
      if (!source.includes(originalDefaultFallback) || !source.includes(originalLoaderFailure)) {
        throw new Error(
          "AFCON360 could not match the expected Expo SDK DevLauncher failure paths. " +
          "Refusing an unverified native source modification."
        );
      }

      const patchedSource = source
        .replace(originalDefaultFallback, patchedDefaultFallback)
        .replace(originalLoaderFailure, patchedLoaderFailure);
      fs.writeFileSync(controllerPath, patchedSource, "utf8");
      console.log(
        "AFCON360 automatic fallback enabled: Metro -> EAS Update -> embedded app -> launcher only if all app sources fail."
      );
      return modConfig;
    },
  ]);
};
