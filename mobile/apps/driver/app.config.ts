import type { ExpoConfig } from "expo/config";

const isPreview = process.env.AFCON360_PREVIEW_BUILD === "true";
const appId = "space.pamoja.afcon360.driver" + (isPreview ? ".preview" : "");
const easProjectId = (
  process.env.AFCON360_DRIVER_EAS_PROJECT_ID ?? process.env.EAS_PROJECT_ID
)?.trim();
const updateChannel = isPreview ? "driver-preview" : "driver-production";
const updatesEnabled = Boolean(easProjectId);

// This app config defines the binary runtime contract. Changes to its native
// update configuration require one fresh APK; later JS-only changes use OTA.

const config: ExpoConfig = {
  name: isPreview ? "AFCON360 Driver Preview" : "AFCON360 Driver",
  slug: "afcon360-driver",
  scheme: isPreview ? "afcon360-driver-preview" : "afcon360-driver",
  version: "1.0.0",
  // Native fingerprints keep JavaScript-only changes compatible with the
  // installed binary, while forcing a new runtime when native dependencies
  // or generated native configuration genuinely change.
  runtimeVersion: { policy: "fingerprint" },
  updates: updatesEnabled && easProjectId
    ? {
        url: `https://u.expo.dev/${easProjectId}`,
        requestHeaders: { "expo-channel-name": updateChannel },
        checkAutomatically: "ON_LOAD",
        fallbackToCacheTimeout: 0,
        maxUpdatesToKeep: 3
      }
    : { enabled: false },
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
    versionCode: Math.max(1, Number.parseInt(process.env.AFCON360_ANDROID_VERSION_CODE ?? "1", 10) || 1),
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
    apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://www.pamoja.space",
    ...(easProjectId ? { eas: { projectId: easProjectId } } : {})
  }
};

export default config;
