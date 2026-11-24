import type { ExpoConfig } from "expo/config";

const isPreview = process.env.AFCON360_PREVIEW_BUILD === "true";
const isReleaseBuild = process.env.AFCON360_RELEASE_BUILD === "true";
const isDevelopmentClient = process.env.AFCON360_DEVELOPMENT_CLIENT === "true";
if (isDevelopmentClient && !isPreview) {
  throw new Error("AFCON360 development-client builds must use the internal preview identity.");
}
const appId = "space.pamoja.afcon360.user" + (isPreview ? ".preview" : "") + (isDevelopmentClient ? ".dev" : "");
const appScheme = isDevelopmentClient ? "afcon360-preview-dev" : isPreview ? "afcon360-preview" : "afcon360";
const easProjectId =
  process.env.AFCON360_USER_EAS_PROJECT_ID?.trim() ||
  process.env.EAS_BUILD_PROJECT_ID?.trim();
const isEasBuild = process.env.EAS_BUILD === "true";
const isE2EBuild = process.env.AFCON360_E2E_BUILD === "true";
// CI E2E and the installable developer APK use separate isolated channels.
// Neither publishes unreviewed feature code to the user-facing preview channel.
const previewUpdateChannel =
  process.env.AFCON360_UPDATE_CHANNEL?.trim() || "preview";

// These isolated development channels must remain local-first even when
// EAS Preview environment variables contain the public production API URL.
// A saved tester-selected server still takes precedence inside the API client.
const isLocalFirstDevelopmentChannel =
  isE2EBuild ||
  (isPreview &&
    (isDevelopmentClient ||
      ["user-development", "user-development-client"].includes(previewUpdateChannel)));
if (
  isPreview &&
  !["preview", "user-development", "user-development-client"].includes(previewUpdateChannel)
) {
  throw new Error("AFCON360 preview builds may use only preview or user-development update channels.");
}
const updateChannel = isE2EBuild
  ? "afcon360-user-e2e"
  : isPreview
  ? previewUpdateChannel
  : "production";

// When Metro is unavailable, the development client can fall back to the
// latest compatible EAS update on its isolated development channel. Metro
// remains the first choice after a developer has connected to it at least once.
const developmentClientFallbackUrl =
  isDevelopmentClient && easProjectId
    ? "https://u.expo.dev/" + easProjectId + "?channel-name=" + updateChannel
    : undefined;

const easProjectIdPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
if (easProjectId && !easProjectIdPattern.test(easProjectId)) {
  throw new Error("AFCON360 User EAS project ID must be a valid UUID.");
}
if (isEasBuild && !easProjectId) {
  throw new Error(
    "AFCON360 User EAS builds require the dedicated EAS project ID. " +
      "Configure AFCON360_USER_EAS_PROJECT_ID or confirm EAS_BUILD_PROJECT_ID is available."
  );
}

const apiBaseUrl = isLocalFirstDevelopmentChannel
  ? "http://127.0.0.1:5000"
  : process.env.EXPO_PUBLIC_API_BASE_URL?.trim() || "https://www.pamoja.space";
let parsedApiBaseUrl: URL;
try {
  parsedApiBaseUrl = new URL(apiBaseUrl);
} catch {
  throw new Error("AFCON360 User API base URL must be an absolute HTTP(S) URL.");
}
if (!["https:", "http:"].includes(parsedApiBaseUrl.protocol)) {
  throw new Error("AFCON360 User API base URL must use HTTP or HTTPS.");
}
const apiHostname = parsedApiBaseUrl.hostname.toLowerCase();
const isLoopbackApi =
  apiHostname === "localhost" ||
  apiHostname.endsWith(".localhost") ||
  /^127(?:\.\d{1,3}){3}$/.test(apiHostname) ||
  apiHostname === "0.0.0.0" ||
  apiHostname === "::1" ||
  apiHostname === "[::1]" ||
  apiHostname.endsWith(".local");
if (isReleaseBuild && (parsedApiBaseUrl.protocol !== "https:" || isLoopbackApi)) {
  throw new Error(
    "AFCON360 production builds must use an HTTPS API endpoint and cannot target localhost."
  );
}

const config: ExpoConfig = {
  name: isDevelopmentClient ? "AFCON360 Developer" : isPreview ? "AFCON360 Preview" : "AFCON360",
  slug: "afcon360-user",
  scheme: appScheme,
  version: "1.0.2",
  // Native fingerprint changes produce a new runtime version automatically.
  // JS/TS-only changes keep the same runtime and remain OTA-compatible.
  runtimeVersion: { policy: "fingerprint" },
  developmentClient: isDevelopmentClient ? { silentLaunch: true } : undefined,
  updates: easProjectId
    ? {
        url: "https://u.expo.dev/" + easProjectId,
        requestHeaders: { "expo-channel-name": updateChannel },
        checkAutomatically: "ON_LOAD",
        // The CI-only channel waits briefly for the just-published test bundle;
        // user-facing builds retain immediate startup with background download.
        fallbackToCacheTimeout: isE2EBuild ? 30_000 : 0
      }
    : undefined,
  orientation: "default",
  userInterfaceStyle: "automatic",
  ios: {
    bundleIdentifier: appId,
    deploymentTarget: "16.4",
    supportsTablet: true
  },
  android: {
    package: appId,
    // Initial EAS remote version seed; EAS auto-increments this for every managed build.
    versionCode: 1,
    allowBackup: false,
    // Use the Android system photo/document picker instead of broad legacy storage.
    // The User app does not require full-screen overlay access.
    blockedPermissions: [
      "android.permission.READ_EXTERNAL_STORAGE",
      "android.permission.WRITE_EXTERNAL_STORAGE",
      "android.permission.SYSTEM_ALERT_WINDOW"
    ],
    adaptiveIcon: { backgroundColor: "#087A4B" }
  },
  plugins: [
    "expo-router",
    [
      "./plugins/withPreviewCleartextTraffic",
      { enabled: isPreview }
    ],
    "./plugins/withReactNativeGradlePluginPortal",
    "expo-secure-store",
    ["expo-sqlite", { useSQLCipher: true }],
    [
      "expo-dev-client",
      isDevelopmentClient
        ? {
            launchMode: "most-recent",
            defaultLaunchURL: developmentClientFallbackUrl,
            embeddedBundle: true,
            skipOnboarding: true,
            showMenuAtLaunch: false,
            toolsButton: false
          }
        : {}
    ],
    ["./plugins/withDevClientEmbeddedBundle", { enabled: isDevelopmentClient }],
    "expo-updates",
    [
      "expo-location",
      {
        locationWhenInUsePermission: "AFCON360 uses your location only when you choose Use my current location to set your ride pickup."
      }
    ]
  ],
  extra: {
    apiBaseUrl,
    allowServerSelection: isPreview,
    ...(easProjectId ? { eas: { projectId: easProjectId } } : {})
  }
};

export default config;
