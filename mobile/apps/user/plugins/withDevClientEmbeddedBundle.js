"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { withAppBuildGradle, withDangerousMod } = require("expo/config-plugins");

/**
 * AFCON360's single development APK needs three compatible sources:
 * 1. Metro for active development and Fast Refresh.
 * 2. The latest compatible EAS Update when Metro is unavailable.
 * 3. The embedded JS bundle if neither Metro nor a usable EAS update can load.
 *
 * React Native Gradle Plugin normally omits the JS bundle for debuggable
 * variants. Removing "debug" from debuggableVariants embeds the bundle while
 * retaining expo-dev-client and its Metro support.
 *
 * SDK 58's DevLauncher falls back from a failed defaultLaunchURL to its
 * launcher screen. Patch that one failure path to try the bundled JS before
 * showing the launcher. This patch is version-structure guarded.
 */
module.exports = function withDevClientEmbeddedBundle(config, options = {}) {
  if (options.enabled !== true) return config;

  config = withAppBuildGradle(config, (modConfig) => {
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
          "AFCON360 could not locate SDK 58 DevLauncherController.kt. " +
          "The automatic embedded fallback patch must be reviewed for the installed Expo SDK."
        );
      }

      const source = fs.readFileSync(controllerPath, "utf8");
      const original = [
        "      } catch (_: Throwable) {",
        "        navigateToLauncher()",
        "      }",
        "    }",
        "  }",
        "",
        "  override fun handleIntent",
      ].join("\n");
      const patched = [
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

      if (source.includes(patched)) {
        console.log("AFCON360 automatic embedded-bundle fallback is already patched.");
        return modConfig;
      }
      if (!source.includes(original)) {
        throw new Error(
          "AFCON360 could not match the expected SDK 58 DevLauncher fallback block. " +
          "Refusing to make an unverified change to expo-dev-launcher."
        );
      }

      fs.writeFileSync(controllerPath, source.replace(original, patched), "utf8");
      console.log(
        "AFCON360 patched Metro/EAS failure handling: load embedded JS before showing the developer launcher."
      );
      return modConfig;
    },
  ]);
};
