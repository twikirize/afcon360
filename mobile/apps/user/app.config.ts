import type { ExpoConfig } from "expo/config";

const config: ExpoConfig = {
  name: "AFCON360",
  slug: "afcon360-user",
  scheme: "afcon360",
  version: "1.0.0",
  orientation: "default",
  userInterfaceStyle: "automatic",
  ios: { bundleIdentifier: "space.pamoja.afcon360.user", deploymentTarget: "16.4", supportsTablet: true },
  android: {
    package: "space.pamoja.afcon360.user",
    allowBackup: false,
    // Use the Android system photo/document picker for future user-selected uploads.
    // The User app does not need broad legacy shared-storage or overlay access.
    blockedPermissions: [
      "android.permission.READ_EXTERNAL_STORAGE",
      "android.permission.WRITE_EXTERNAL_STORAGE",
      "android.permission.SYSTEM_ALERT_WINDOW"
    ],
    adaptiveIcon: { backgroundColor: "#087A4B" }
  },
  plugins: ["expo-router", "expo-secure-store", "expo-dev-client"],
  extra: { apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://www.pamoja.space" }
};

export default config;
