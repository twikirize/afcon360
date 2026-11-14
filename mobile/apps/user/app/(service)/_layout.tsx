import React from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { Redirect, Stack } from "expo-router";
import { palette } from "@afcon360/mobile-ui";
import { useAuth } from "../../src/auth/AuthProvider";
import { UserDashboardHeader } from "../../src/components/UserDashboardHeader";

const USER_PRIMARY = "#0E4CCD";

export default function UserServiceRoutes() {
  const { user, loading, restoreError, retryRestoreSession } = useAuth();

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: palette.canvas }}>
        <ActivityIndicator color={USER_PRIMARY} />
      </View>
    );
  }

  if (restoreError) return <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 24, backgroundColor: palette.canvas }}><Text style={{ color: palette.ink, textAlign: "center", lineHeight: 22 }}>{restoreError}</Text><Pressable accessibilityRole="button" onPress={() => void retryRestoreSession()} style={{ marginTop: 16, padding: 14, backgroundColor: USER_PRIMARY, borderRadius: 10 }}><Text style={{ color: "#FFFFFF", fontWeight: "800" }}>Retry saved session</Text></Pressable></View>;
  if (!user) return <Redirect href="/login" />;

  return <Stack screenOptions={{ headerShown: true, header: () => <UserDashboardHeader /> }} />;
}
