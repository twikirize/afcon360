import type { ExpoConfig } from "expo/config";
const config: ExpoConfig = {
  name: "AFCON360 Driver", slug: "afcon360-driver", scheme: "afcon360-driver",
  version: "1.0.0", orientation: "default", userInterfaceStyle: "automatic",
  ios: {
    bundleIdentifier: "space.pamoja.afcon360.driver", deploymentTarget: "16.4", supportsTablet: true,
    infoPlist: { NSLocationWhenInUseUsageDescription: "AFCON360 Driver uses your location while you are using the app to support availability and trip navigation." }
  },
  android: { package: "space.pamoja.afcon360.driver", adaptiveIcon: { backgroundColor: "#087A4B" } },
  plugins: [
    "expo-router", "expo-secure-store", "expo-dev-client",
    ["expo-location", { locationWhenInUsePermission: "Allow AFCON360 Driver to use your location while you are using the app for availability and trip navigation." }]
  ],
  extra: { apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://www.pamoja.space" }
};
export default config;
