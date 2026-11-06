import React from "react";
import { Redirect, Tabs } from "expo-router";
import { Text } from "react-native";
import { palette } from "@afcon360/mobile-ui";
import { ActivityIndicator, View } from "react-native";
import { useAuth } from "../../src/auth/AuthProvider";
const symbols: Record<string, string> = { index: "⌂", explore: "◇", activity: "↗", wallet: "◈", account: "○" };
export default function UserTabs() {
  const { user, loading } = useAuth();
  if (loading) return <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: palette.canvas }}><ActivityIndicator color={palette.green} /></View>;
  if (!user) return <Redirect href="/login" />;
  return <Tabs screenOptions={({ route }) => ({
    headerShown: false,
    tabBarActiveTintColor: palette.green,
    tabBarInactiveTintColor: palette.muted,
    tabBarLabelStyle: { fontSize: 10, fontWeight: "700" },
    tabBarStyle: { height: 66, paddingTop: 7, paddingBottom: 8, borderTopColor: palette.border, backgroundColor: palette.surface },
    tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 21, fontWeight: "700" }}>{symbols[route.name] ?? "•"}</Text>
  })}>
    <Tabs.Screen name="index" options={{ title: "Home" }} />
    <Tabs.Screen name="explore" options={{ title: "Explore" }} />
    <Tabs.Screen name="stays" options={{ href: null }} />
    <Tabs.Screen name="events" options={{ href: null }} />
    <Tabs.Screen name="activity" options={{ title: "Activity" }} />
    <Tabs.Screen name="wallet" options={{ title: "Wallet" }} />
    <Tabs.Screen name="account" options={{ title: "Account" }} />
  </Tabs>;
}
