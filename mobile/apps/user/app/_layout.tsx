import React from "react";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { Platform, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { palette } from "@afcon360/mobile-ui";
import { AuthProvider } from "../src/auth/AuthProvider";

const ANDROID_EDGE_TO_EDGE_API_LEVEL = 35;
const ANDROID_SYSTEM_NAVIGATION_FALLBACK_DP = 24;

function AppNavigator() {
  const insets = useSafeAreaInsets();
  const usesAndroidEdgeToEdge =
    Platform.OS === "android" &&
    Number(Platform.Version) >= ANDROID_EDGE_TO_EDGE_API_LEVEL;

  // Android 15+ draws the app behind the system navigation bar. Reserve the
  // measured bottom inset at the root so every User screen and its tab bar
  // stay above Back / Home / Recent. Keep a small fallback for devices that
  // report an incomplete transparent-navigation-bar inset.
  const bottomSystemInset = usesAndroidEdgeToEdge
    ? Math.max(insets.bottom, ANDROID_SYSTEM_NAVIGATION_FALLBACK_DP)
    : 0;

  return (
    <View
      style={{
        flex: 1,
        paddingBottom: bottomSystemInset,
        backgroundColor: palette.surface
      }}
    >
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }} />
    </View>
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <AppNavigator />
    </AuthProvider>
  );
}
