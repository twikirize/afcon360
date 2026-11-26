import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const mobileRoot = path.resolve(scriptDir, "..");
const userRoot = path.join(mobileRoot, "apps", "user");
const configPath = process.argv[2];

function fail(message) {
  throw new Error(message);
}

if (!configPath) {
  fail("Usage: node verify-user-dev-delivery-contract.mjs <resolved-expo-config.json>");
}

const raw = fs.readFileSync(configPath, "utf8");
const config = JSON.parse(raw.replace(/^\uFEFF/, ''));
const eas = JSON.parse(fs.readFileSync(path.join(userRoot, "eas.json"), "utf8"));
const appConfigSource = fs.readFileSync(path.join(userRoot, "app.config.ts"), "utf8");
const gradlePlugin = fs.readFileSync(
  path.join(userRoot, "plugins", "withDevClientEmbeddedBundle.js"),
  "utf8",
);
const fingerprintConfig = fs.readFileSync(
  path.join(userRoot, "fingerprint.config.js"),
  "utf8",
);

const workflowSource = fs.readFileSync(
  path.resolve(mobileRoot, "..", ".github", "workflows", "mobile-workspace.yml"),
  "utf8",
);

const checks = [];
const add = (label, passed, detail = "") => checks.push({ label, passed: Boolean(passed), detail });

const profile = eas.build?.development;
add("development profile is an internal APK build",
  profile?.developmentClient === true &&
  profile?.distribution === "internal" &&
  profile?.android?.buildType === "apk");
add("development profile uses its isolated EAS update channel",
  profile?.channel === "user-development-client" &&
  profile?.env?.AFCON360_UPDATE_CHANNEL === "user-development-client");
add("development profile builds the isolated preview developer identity",
  profile?.env?.AFCON360_PREVIEW_BUILD === "true" &&
  profile?.env?.AFCON360_RELEASE_BUILD === "false" &&
  profile?.env?.AFCON360_DEVELOPMENT_CLIENT === "true");
add("development profile defaults to the laptop API origin",
  profile?.env?.EXPO_PUBLIC_API_BASE_URL === "http://127.0.0.1:5000");

add("resolved app package is isolated from Preview and Driver apps",
  config.android?.package === "space.pamoja.afcon360.user.preview.dev");
add("resolved app has the expected developer launch scheme",
  (Array.isArray(config.scheme) ? config.scheme : [config.scheme]).includes("afcon360-preview-dev"));
add("development client uses silent launch",
  config.developmentClient?.silentLaunch === true);
add("Metro launch mode prefers the most recently connected project",
  config.plugins?.some(plugin =>
    Array.isArray(plugin) &&
    plugin[0] === "expo-dev-client" &&
    plugin[1]?.launchMode === "most-recent"));
const devClientPlugin = config.plugins?.find(plugin =>
  Array.isArray(plugin) && plugin[0] === "expo-dev-client")?.[1];
add("Metro-off fallback targets the EAS development channel",
  devClientPlugin?.defaultLaunchURL ===
    "https://u.expo.dev/" + config.extra?.eas?.projectId + "?channel-name=user-development-client");
add("embedded bundle option is enabled in the development client",
  devClientPlugin?.embeddedBundle === true);
add("development client suppresses launcher onboarding and menu at startup",
  devClientPlugin?.skipOnboarding === true &&
  devClientPlugin?.showMenuAtLaunch === false);
add("native Gradle plugin ships a JS bundle in the debug variant",
  /debuggableVariants\s*=\s*\[\s*\]/.test(gradlePlugin));
add("app config enables the native embedded-bundle and automatic fallback plugin only for development clients",
  appConfigSource.includes('withDevClientEmbeddedBundle') &&
  appConfigSource.includes('enabled: isDevelopmentClient'));
add("native fallback plugin is included in the fingerprint with valid reasons metadata",
  fingerprintConfig.includes('filePath: "plugins/withDevClientEmbeddedBundle.js"') &&
  fingerprintConfig.includes('reasons: ["AFCON360\'s Metro and embedded-bundle startup fallback"]'));
add("native fingerprint preflight runs before any candidate APK build",
  workflowSource.includes("node ../../scripts/user-native-fingerprint.cjs") &&
  workflowSource.indexOf("Validate hybrid Metro and EAS development delivery configuration") <
    workflowSource.indexOf("  build-user-dev-apk:"));
add("native plugin automatically falls back to embedded JS after Metro and EAS loading fail",
  gradlePlugin.includes("loadEmbeddedBundle(activityToBeInvalidated)") &&
  gradlePlugin.includes("loadEmbeddedBundle(mainActivity)") &&
  gradlePlugin.includes("DevLauncherController.kt") &&
  gradlePlugin.includes("replace(originalDefaultFallback, patchedDefaultFallback)") &&
  gradlePlugin.includes("replace(originalLoaderFailure, patchedLoaderFailure)") &&
  gradlePlugin.includes("Refusing an unverified native source modification"));

add("expo-updates is installed as a native plugin",
  config.plugins?.some(plugin =>
    plugin === "expo-updates" ||
    (Array.isArray(plugin) && plugin[0] === "expo-updates")));
add("EAS Updates use the isolated development channel",
  config.updates?.url === "https://u.expo.dev/" + config.extra?.eas?.projectId &&
  config.updates?.requestHeaders?.["expo-channel-name"] === "user-development-client");
add("EAS update checks do not delay ordinary bundle startup",
  config.updates?.checkAutomatically === "ON_LOAD" &&
  config.updates?.fallbackToCacheTimeout === 0);
const productionProfile = eas.build?.production;

add(
  "Internal development uses app-version runtime while production retains native fingerprint compatibility",
  config.runtimeVersion?.policy === "appVersion" &&
    productionProfile?.environment === "production" &&
    productionProfile?.channel === "production" &&
    productionProfile?.env?.AFCON360_RELEASE_BUILD === "true" &&
    productionProfile?.env?.AFCON360_PREVIEW_BUILD === "false" &&
    /const isReleaseBuild = process\.env\.AFCON360_RELEASE_BUILD === "true"/.test(appConfigSource) &&
    /runtimeVersion:\s*isReleaseBuild\s*\?\s*\{\s*policy:\s*"fingerprint"\s*\}\s*:\s*\{\s*policy:\s*"appVersion"\s*\}/.test(appConfigSource)
);
add("laptop/live backend selection is enabled independently of Metro",
  config.extra?.allowServerSelection === true &&
  config.extra?.apiBaseUrl === "http://127.0.0.1:5000" &&
  appConfigSource.includes("const isLocalFirstDevelopmentChannel"));

const failures = checks.filter(item => !item.passed);
for (const item of checks) {
  process.stdout.write(
    (item.passed ? "PASS " : "FAIL ") + item.label +
    (item.detail ? " — " + item.detail : "") + "\n"
  );
}

if (failures.length) {
  process.stderr.write(
    "\nUser development delivery contract failed " +
    failures.length + " of " + checks.length + " checks.\n"
  );
  process.exit(1);
}

process.stdout.write(
  "\nPASS: all " + checks.length +
  " User development delivery configuration checks passed.\n"
);
