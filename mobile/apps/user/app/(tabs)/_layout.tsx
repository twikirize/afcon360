import React from "react";
import { Redirect, Tabs } from "expo-router";
import { Pressable, Text } from "react-native";
import { palette } from "@afcon360/mobile-ui";
import { ActivityIndicator, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "../../src/auth/AuthProvider";
const symbols: Record<string, string> = { index: "⌂", explore: "◇", activity: "↗", wallet: "◈", account: "○" };
export default function UserTabs() {
  const insets = useSafeAreaInsets();
  const { user, loading, restoreError, retryRestoreSession } = useAuth();
  if (loading) return <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: palette.canvas }}><ActivityIndicator color={palette.green} /></View>;
  if (restoreError) return <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 24, backgroundColor: palette.canvas }}><Text style={{ color: palette.ink, textAlign: "center", lineHeight: 22 }}>{restoreError}</Text><Pressable accessibilityRole="button" onPress={() => void retryRestoreSession()} style={{ marginTop: 16, padding: 14, backgroundColor: palette.green, borderRadius: 10 }}><Text style={{ color: "#FFFFFF", fontWeight: "800" }}>Retry saved session</Text></Pressable></View>;
  if (!user) return <Redirect href="/login" />;
  return <Tabs screenOptions={({ route }) => ({
    headerShown: false,
    tabBarActiveTintColor: palette.green,
    tabBarInactiveTintColor: palette.muted,
    tabBarLabelStyle: { fontSize: 10, fontWeight: "700" },
    // Keep the custom 66dp tab content above Android's system navigation
    // bar and iOS's home indicator. A fixed 66dp height with no bottom inset
    // places the Activity/Wallet/Account touch targets underneath system UI.
    tabBarStyle: {
      height: 66 + insets.bottom,
      paddingTop: 7,
      paddingBottom: 8 + insets.bottom,
      borderTopColor: palette.border,
      backgroundColor: palette.surface
    },
    tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 21, fontWeight: "700" }}>{symbols[route.name] ?? "•"}</Text>
  })}>
    <Tabs.Screen name="index" options={{ title: "Home" }} />
    <Tabs.Screen name="explore" options={{ title: "Explore" }} />
    <Tabs.Screen name="activity" options={{ title: "Activity" }} />
    <Tabs.Screen name="wallet" options={{ title: "Wallet" }} />
    <Tabs.Screen name="account" options={{ title: "Account" }} />
  </Tabs>;
}
