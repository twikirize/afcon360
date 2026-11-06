import type { ExpoConfig } from "expo/config";

const isPreview = process.env.AFCON360_PREVIEW_BUILD === "true";
const appId = "space.pamoja.afcon360.user" + (isPreview ? ".preview" : "");

const config: ExpoConfig = {
  name: isPreview ? "AFCON360 Preview" : "AFCON360",
  slug: "afcon360-user",
  scheme: isPreview ? "afcon360-preview" : "afcon360",
  version: "1.0.0",
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
  plugins: ["expo-router", "expo-secure-store", "expo-dev-client"],
  extra: {
    apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://www.pamoja.space"
  }
};

export default config;
