import type { ExpoConfig } from "expo/config";

const config: ExpoConfig = {
  name: "AFCON360",
  slug: "afcon360-user",
  scheme: "afcon360",
  version: "1.0.0",
  orientation: "default",
  userInterfaceStyle: "automatic",
  ios: { bundleIdentifier: "space.pamoja.afcon360.user", supportsTablet: true },
  android: { package: "space.pamoja.afcon360.user", adaptiveIcon: { backgroundColor: "#087A4B" } },
  plugins: ["expo-router", "expo-secure-store"],
  extra: { apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "" }
};

export default config;
