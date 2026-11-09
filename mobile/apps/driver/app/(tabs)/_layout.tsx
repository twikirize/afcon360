import React from "react";
import { Redirect, Tabs } from "expo-router";
import { Text, View, ActivityIndicator } from "react-native";
import { palette } from "@afcon360/mobile-ui";
import { useAuth } from "../../src/auth/AuthProvider";

const symbols: Record<string, string> = {
  index: "⌂",
  status: "◉",
  trips: "↗",
  earnings: "◈",
  assignments: "⇄",
  vehicles: "▣",
  account: "○"
};

export default function DriverTabs() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: palette.canvas }}>
        <ActivityIndicator color={palette.green} />
      </View>
    );
  }
  if (!user) return <Redirect href="/login" />;

  return (
    <Tabs
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: palette.green,
        tabBarInactiveTintColor: palette.muted,
        tabBarLabelStyle: { fontSize: 9, fontWeight: "700" },
        tabBarStyle: {
          height: 68,
          paddingTop: 6,
          paddingBottom: 8,
          borderTopColor: palette.border,
          backgroundColor: palette.surface
        },
        tabBarIcon: ({ color }) => (
          <Text style={{ color, fontSize: 20, fontWeight: "700" }}>
            {symbols[route.name] ?? "•"}
          </Text>
        )
      })}
    >
      <Tabs.Screen name="index" options={{ title: "Home" }} />
      <Tabs.Screen name="status" options={{ title: "Status" }} />
      <Tabs.Screen name="trips" options={{ title: "Trips" }} />
      <Tabs.Screen name="earnings" options={{ title: "Earnings" }} />
      <Tabs.Screen name="assignments" options={{ title: "Assignments" }} />
      <Tabs.Screen name="vehicles" options={{ title: "Vehicles" }} />
      <Tabs.Screen name="account" options={{ title: "Account" }} />
    </Tabs>
  );
}
