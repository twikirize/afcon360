import type { ExpoConfig } from "expo/config";

const isPreview = process.env.AFCON360_PREVIEW_BUILD === "true";
const appId = "space.pamoja.afcon360.user" + (isPreview ? ".preview" : "");
const easProjectId = process.env.AFCON360_USER_EAS_PROJECT_ID?.trim();
const updateChannel = isPreview ? "preview" : "production";

const config: ExpoConfig = {
  name: isPreview ? "AFCON360 Preview" : "AFCON360",
  slug: "afcon360-user",
  scheme: isPreview ? "afcon360-preview" : "afcon360",
  version: "1.0.0",
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
  plugins: ["expo-router", "expo-secure-store", "expo-dev-client", "expo-updates"],
  extra: {
    apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://www.pamoja.space",
    allowServerSelection: isPreview,
    ...(easProjectId ? { eas: { projectId: easProjectId } } : {})
  }
};

export default config;
