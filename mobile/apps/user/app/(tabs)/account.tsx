import React from "react";
import { Alert, Share, Text } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, StatusPill, ActionButton, palette } from "@afcon360/mobile-ui";
import { useAuth } from "../../src/auth/AuthProvider";
import { SERVER_SELECTION_ENABLED } from "../../src/services/api";

export default function Account() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const signOut = async () => {
    try {
      await logout();
      router.replace("/login");
    } catch {
      // Local credentials are cleared by AuthProvider even if the server is
      // unreachable. Tell the user that remote revocation could not be proven.
      router.replace("/login");
      Alert.alert(
        "Server sign-out not confirmed",
        "This device has been signed out, but AFCON360 could not confirm that the server session was revoked. Connect to the internet and sign in again to refresh your session, and review any other devices where you are signed in."
      );
    }
  };

  const share = async (url: string, message: string) => {
    try { await Share.share({ message: message + " " + url, url }); }
    catch { Alert.alert("Share unavailable", "Copy this link: " + url); }
  };
  return <AppScreen>
    <PageHeader eyebrow="Account" title="Your AFCON360 identity." description="Your account, roles and verification state are owned by AFCON360 identity services." />
    <Panel>
      <StatusPill>Signed in securely</StatusPill>
      <SectionTitle>{user?.display_name ?? user?.username ?? "Your account"}</SectionTitle>
      <Text style={{ color: palette.muted, fontSize: 12 }}>{user?.email ?? ""}</Text>
      <ServiceTile title="Identity and verification" description="Profile and KYC status are returned by AFCON360 Identity." symbol="✓" />
      <ServiceTile title="Secure device session" description="Access credentials are kept in the device secure store and can be revoked by signing out." symbol="🔐" />
      <ActionButton label="Share AFCON360 app page" onPress={() => share("https://www.pamoja.space/apps", "AFCON360 — official app information and downloads.")} />
      <ActionButton label="Privacy notice (website)" onPress={() => WebBrowser.openBrowserAsync("https://www.pamoja.space/apps/privacy")} />
      {SERVER_SELECTION_ENABLED ? <ActionButton label="Connection settings (preview)" onPress={() => router.push("/server-settings" as never)} /> : null}
      <ActionButton label="Delete AFCON360 account" onPress={() => router.push("/(service)/delete-account" as never)} />
      <ActionButton label="Sign out" onPress={() => Alert.alert("Sign out", "Sign out of AFCON360 on this device?", [{ text: "Cancel", style: "cancel" }, { text: "Sign out", onPress: () => { void signOut(); } }])} />
    </Panel>
    <Text style={{ color: palette.muted, fontSize: 12 }}>Privacy and support: pamoja.space/support</Text>
  </AppScreen>;
}
