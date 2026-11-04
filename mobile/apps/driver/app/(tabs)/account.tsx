import React from "react";
import { Alert, Share, Text } from "react-native";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, StatusPill, ActionButton, palette } from "@afcon360/mobile-ui";
import { useAuth } from "../../src/auth/AuthProvider";

export default function DriverAccount() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const share = async () => {
    try { await Share.share({ message: "AFCON360 Driver — get the official app and driver information: https://www.pamoja.space/apps", url: "https://www.pamoja.space/apps" }); }
    catch { Alert.alert("Share unavailable", "Copy this link: https://www.pamoja.space/apps"); }
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
      <ActionButton label="Share AFCON360 Driver" onPress={share} />
      <ActionButton label="Delete AFCON360 account" onPress={() => router.push("/delete-account")} />
      <ActionButton label="Sign out" onPress={() => Alert.alert("Sign out", "Sign out this driver device?", [{ text: "Cancel", style: "cancel" }, { text: "Sign out", onPress: () => logout().then(() => router.replace("/login")).catch(() => router.replace("/login")) }])} />
    </Panel>
    <Text style={{ color: palette.muted, fontSize: 12 }}>Privacy and support: pamoja.space/support</Text>
  </AppScreen>;
}
