import React from "react";
import { Alert, Share, Text } from "react-native";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, StatusPill, ActionButton, palette } from "@afcon360/mobile-ui";
import { useAuth } from "../../src/auth/AuthProvider";

export default function Account() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const share = async () => {
    try { await Share.share({ message: "AFCON360 — travel, transport, stays and experiences across East Africa: https://www.pamoja.space/apps", url: "https://www.pamoja.space/apps" }); }
    catch { Alert.alert("Share unavailable", "Copy this link: https://www.pamoja.space/apps"); }
  };
  return <AppScreen>
    <PageHeader eyebrow="Account" title="Your AFCON360 identity." description="Your account, roles and verification state are owned by AFCON360 identity services." />
    <Panel>
      <StatusPill>Signed in securely</StatusPill>
      <SectionTitle>{user?.display_name ?? user?.username ?? "Your account"}</SectionTitle>
      <Text style={{ color: palette.muted, fontSize: 12 }}>{user?.email ?? ""}</Text>
      <ServiceTile title="Identity and verification" description="Profile and KYC status are returned by AFCON360 Identity." symbol="✓" />
      <ServiceTile title="Secure device session" description="Access credentials are kept in the device secure store and can be revoked by signing out." symbol="🔐" />
      <ActionButton label="Share AFCON360" onPress={share} />
      <ActionButton label="Delete AFCON360 account" onPress={() => router.push("/delete-account")} />
      <ActionButton label="Sign out" onPress={() => Alert.alert("Sign out", "Sign out of AFCON360 on this device?", [{ text: "Cancel", style: "cancel" }, { text: "Sign out", onPress: () => logout().then(() => router.replace("/login")).catch(() => router.replace("/login")) }])} />
    </Panel>
    <Text style={{ color: palette.muted, fontSize: 12 }}>Privacy and support: pamoja.space/support</Text>
  </AppScreen>;
}
