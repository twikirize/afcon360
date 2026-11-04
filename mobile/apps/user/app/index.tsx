import React from "react";
import { Redirect } from "expo-router";
import { ActivityIndicator, View } from "react-native";
import { useAuth } from "../src/auth/AuthProvider";
import { palette } from "@afcon360/mobile-ui";
export default function Index() {
  const { user, loading } = useAuth();
  if (loading) return <View style={{flex:1,alignItems:"center",justifyContent:"center",backgroundColor:palette.canvas}}><ActivityIndicator color={palette.green} /></View>;
  return <Redirect href={user ? "/(tabs)" : "/login"} />;
}
