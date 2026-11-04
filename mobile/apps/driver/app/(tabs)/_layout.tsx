import React from "react";
import { Tabs } from "expo-router";
import { Text } from "react-native";
import { palette } from "@afcon360/mobile-ui";
const symbols: Record<string, string> = { index: "⌂", trips: "↗", earnings: "◈", account: "○" };
export default function DriverTabs() {
  return <Tabs screenOptions={({ route }) => ({
    headerShown: false, tabBarActiveTintColor: palette.green, tabBarInactiveTintColor: palette.muted,
    tabBarLabelStyle: { fontSize: 10, fontWeight: "700" },
    tabBarStyle: { height: 66, paddingTop: 7, paddingBottom: 8, borderTopColor: palette.border, backgroundColor: palette.surface },
    tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 21, fontWeight: "700" }}>{symbols[route.name] ?? "•"}</Text>
  })}>
    <Tabs.Screen name="index" options={{ title: "Home" }} />
    <Tabs.Screen name="trips" options={{ title: "Trips" }} />
    <Tabs.Screen name="earnings" options={{ title: "Earnings" }} />
    <Tabs.Screen name="account" options={{ title: "Account" }} />
  </Tabs>;
}
