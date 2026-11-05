import React from "react";
import { Alert, Share, Text } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, StatusPill, ActionButton, palette } from "@afcon360/mobile-ui";
import { useAuth } from "../../src/auth/AuthProvider";

export default function DriverAccount() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const share = async (url: string, message: string) => {
    try { await Share.share({ message: message + " " + url, url }); }
    catch { Alert.alert("Share unavailable", "Copy this link: " + url); }
  };
  return <AppScreen>
    <PageHeader eyebrow="Driver account" title="Your AFCON360 identity." description="Your approval, documents, vehicle and operating permissions remain owned by AFCON360." />
    <Panel>
      <StatusPill>Signed in securely</StatusPill>
      <SectionTitle>{user?.display_name ?? user?.username ?? "Driver account"}</SectionTitle>
      <Text style={{ color: palette.muted, fontSize: 12 }}>{user?.email ?? ""}</Text>
      <ServiceTile title="Identity and compliance" description="Driver approval and verification status are checked by AFCON360 on every protected action." symbol="✓" />
      <ServiceTile title="Vehicle assignment" description="Vehicle ownership and assignment remain controlled by Transport." symbol="🚙" />
      <ServiceTile title="Support and safety" description="Safety and incident support is available through AFCON360." symbol="🛟" />
      <ActionButton label="Share AFCON360 Driver page" onPress={() => share("https://www.pamoja.space/apps", "AFCON360 Driver — official app information and downloads.")} />
      <ActionButton label="Share Android Driver APK" onPress={() => share("https://github.com/twikirize/afcon360/releases/download/mobile-preview/AFCON360-Driver-preview.apk", "AFCON360 Driver internal Android preview APK. Install only as a test build.")} />
      <ActionButton label="Privacy notice" onPress={() => WebBrowser.openBrowserAsync("https://www.pamoja.space/apps/privacy")} />
      <ActionButton label="Delete AFCON360 account" onPress={() => router.push("/delete-account")} />
      <ActionButton label="Sign out" onPress={() => Alert.alert("Sign out", "Sign out this driver device?", [{ text: "Cancel", style: "cancel" }, { text: "Sign out", onPress: () => logout().then(() => router.replace("/login")).catch(() => router.replace("/login")) }])} />
    </Panel>
    <Text style={{ color: palette.muted, fontSize: 12 }}>Privacy and support: pamoja.space/support</Text>
  </AppScreen>;
}
