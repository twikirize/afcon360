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
  ios: { bundleIdentifier: appId, supportsTablet: true },
  android: { package: appId, adaptiveIcon: { backgroundColor: "#087A4B" } },
  plugins: ["expo-router", "expo-secure-store", "expo-dev-client"],
  extra: { apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://www.pamoja.space" }
};

export default config;
