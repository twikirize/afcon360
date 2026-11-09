import React from "react";
import { ActivityIndicator, View } from "react-native";
import { Redirect, Stack } from "expo-router";
import { palette } from "@afcon360/mobile-ui";
import { useAuth } from "../../src/auth/AuthProvider";

export default function UserServiceRoutes() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: palette.canvas }}>
        <ActivityIndicator color={palette.green} />
      </View>
    );
  }

  if (!user) return <Redirect href="/login" />;

  return <Stack screenOptions={{ headerShown: false }} />;
}
