import type { ExpoConfig } from "expo/config";

const isPreview = process.env.AFCON360_PREVIEW_BUILD === "true";
const appId = "space.pamoja.afcon360.driver" + (isPreview ? ".preview" : "");

const config: ExpoConfig = {
  name: isPreview ? "AFCON360 Driver Preview" : "AFCON360 Driver",
  slug: "afcon360-driver",
  scheme: isPreview ? "afcon360-driver-preview" : "afcon360-driver",
  version: "1.0.0",
  orientation: "default",
  userInterfaceStyle: "automatic",
  ios: {
    bundleIdentifier: appId,
    deploymentTarget: "16.4",
    supportsTablet: true,
    infoPlist: {
      NSLocationWhenInUseUsageDescription:
        "AFCON360 Driver uses your location while you are using the app to support availability and trip navigation."
    }
  },
  android: {
    package: appId,
    allowBackup: false,
    // Use scoped system pickers rather than broad legacy storage permissions.
    // Driver does not require full-screen overlay access.
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
    [
      "expo-location",
      {
        locationWhenInUsePermission:
          "Allow AFCON360 Driver to use your location while you are using the app for availability and trip navigation."
      }
    ]
  ],
  extra: {
    apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://www.pamoja.space"
  }
};

export default config;
