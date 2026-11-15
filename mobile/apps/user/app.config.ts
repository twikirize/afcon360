import type { ExpoConfig } from "expo/config";

const isPreview = process.env.AFCON360_PREVIEW_BUILD === "true";
const isReleaseBuild = process.env.AFCON360_RELEASE_BUILD === "true";
const appId = "space.pamoja.afcon360.user" + (isPreview ? ".preview" : "");
const easProjectId =
  process.env.AFCON360_USER_EAS_PROJECT_ID?.trim() ||
  process.env.EAS_BUILD_PROJECT_ID?.trim();
const isEasBuild = process.env.EAS_BUILD === "true";
const updateChannel = isPreview ? "preview" : "production";

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

const apiBaseUrl =
  process.env.EXPO_PUBLIC_API_BASE_URL?.trim() || "https://www.pamoja.space";
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
  name: isPreview ? "AFCON360 Preview" : "AFCON360",
  slug: "afcon360-user",
  scheme: isPreview ? "afcon360-preview" : "afcon360",
  version: "1.0.1",
  runtimeVersion: { policy: "appVersion" },
  updates: easProjectId
    ? {
        url: `https://u.expo.dev/${easProjectId}`,
        requestHeaders: { "expo-channel-name": updateChannel },
        checkAutomatically: "ON_LOAD",
        fallbackToCacheTimeout: 0
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
    "expo-secure-store",
    "expo-dev-client",
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
