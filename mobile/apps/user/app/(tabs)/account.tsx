import React, { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  Share,
  Text,
  View
} from "react-native";
import Constants from "expo-constants";
import * as Updates from "expo-updates";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, StatusPill, ActionButton, palette } from "@afcon360/mobile-ui";
import { useAuth } from "../../src/auth/AuthProvider";
import { SERVER_SELECTION_ENABLED } from "../../src/services/api";

type UpdateStatus = "idle" | "checking" | "downloading" | "ready" | "current" | "error" | "unavailable";

function AppUpdateControls() {
  const [status, setStatus] = useState<UpdateStatus>("idle");
  const [message, setMessage] = useState(
    "AFCON360 checks for compatible updates when the app starts. You can also check manually here."
  );

  const appVersion = Constants.expoConfig?.version ?? "Unknown";
  const runtimeVersion = Updates.runtimeVersion ?? "Not reported";
  const channel = Updates.channel ?? "Not configured";
  const updateId = Updates.updateId ? Updates.updateId.slice(0, 8) : "Built-in app bundle";
  const busy = status === "checking" || status === "downloading";

  const checkForUpdates = async () => {
    if (__DEV__ || !Updates.isEnabled) {
      setStatus("unavailable");
      setMessage(
        "Over-the-air updates are unavailable in this development session. Open the installed AFCON360 preview app to check for published updates."
      );
      return;
    }

    if (busy) return;

    setStatus("checking");
    setMessage("Checking the " + channel + " update channel…");

    try {
      const check = await Updates.checkForUpdateAsync();

      if (check.isRollBackToEmbedded) {
        setStatus("ready");
        setMessage(
          "A verified rollback to the embedded app version is available. Restart AFCON360 to apply it."
        );
        return;
      }

      if (!check.isAvailable) {
        setStatus("current");
        setMessage(
          "This app is up to date. AFCON360 will continue checking automatically when it starts."
        );
        return;
      }

      setStatus("downloading");
      setMessage("A compatible update was found. Downloading it securely…");

      const result = await Updates.fetchUpdateAsync();
      if (result.isNew) {
        setStatus("ready");
        setMessage(
          "The update has downloaded successfully. Restart AFCON360 to begin using the updated app."
        );
      } else {
        setStatus("current");
        setMessage("No newer compatible update needs to be installed.");
      }
    } catch (error) {
      setStatus("error");
      setMessage(
        error instanceof Error
          ? "Could not check for updates: " + error.message
          : "Could not check for updates. Check your internet connection and try again."
      );
    }
  };

  const applyUpdate = async () => {
    try {
      await Updates.reloadAsync();
    } catch (error) {
      setStatus("error");
      setMessage(
        error instanceof Error
          ? "The update downloaded, but AFCON360 could not restart: " + error.message
          : "The update downloaded, but AFCON360 could not restart. Close and reopen the app."
      );
    }
  };

  return (
    <View style={{
      marginTop: 8,
      padding: 14,
      borderRadius: 14,
      borderWidth: 1,
      borderColor: palette.border,
      backgroundColor: "#F6F8F6",
      gap: 10
    }}>
      <View style={{ gap: 3 }}>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "900" }}>
          App version and updates
        </Text>
        <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 16 }}>
          Keep this installation current without reinstalling the APK for ordinary app improvements.
        </Text>
      </View>

      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 12 }}>
        <Text style={{ color: palette.muted, fontSize: 12 }}>Installed version</Text>
        <Text selectable style={{ color: palette.ink, fontSize: 12, fontWeight: "900" }}>
          {appVersion}
        </Text>
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 12 }}>
        <Text style={{ color: palette.muted, fontSize: 12 }}>Update channel</Text>
        <Text selectable style={{ color: palette.ink, fontSize: 12, fontWeight: "800" }}>
          {channel}
        </Text>
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 12 }}>
        <Text style={{ color: palette.muted, fontSize: 12 }}>Compatible runtime</Text>
        <Text selectable style={{ color: palette.ink, fontSize: 12, fontWeight: "800" }}>
          {runtimeVersion}
        </Text>
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 12 }}>
        <Text style={{ color: palette.muted, fontSize: 12 }}>Running update</Text>
        <Text selectable style={{ color: palette.ink, fontSize: 12, fontWeight: "800" }}>
          {updateId}
        </Text>
      </View>

      <Text accessibilityLiveRegion="polite" style={{
        color: status === "error" ? "#A12E27" : palette.muted,
        fontSize: 11,
        lineHeight: 17
      }}>
        {message}
      </Text>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Check for AFCON360 app updates"
        accessibilityState={{ disabled: busy }}
        disabled={busy}
        onPress={() => void checkForUpdates()}
        style={{
          minHeight: 46,
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "row",
          gap: 8,
          borderRadius: 11,
          backgroundColor: busy ? "#7D9B8B" : palette.green,
          paddingHorizontal: 14,
          paddingVertical: 11,
          opacity: busy ? 0.8 : 1
        }}
      >
        {busy ? <ActivityIndicator color="#FFFFFF" size="small" /> : null}
        <Text style={{ color: "#FFFFFF", fontSize: 12, fontWeight: "900" }}>
          {status === "checking"
            ? "Checking…"
            : status === "downloading"
              ? "Downloading…"
              : status === "error"
                ? "Try checking again"
                : "Check for updates"}
        </Text>
      </Pressable>

      {status === "ready" ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Restart AFCON360 and apply downloaded update"
          onPress={() => void applyUpdate()}
          style={{
            minHeight: 46,
            alignItems: "center",
            justifyContent: "center",
            borderRadius: 11,
            backgroundColor: "#F2C744",
            paddingHorizontal: 14,
            paddingVertical: 11
          }}
        >
          <Text style={{ color: "#173D28", fontSize: 12, fontWeight: "900" }}>
            Restart and apply update
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

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
      <AppUpdateControls />
      <ActionButton label="Share AFCON360 app page" onPress={() => share("https://www.pamoja.space/apps", "AFCON360 — official app information and downloads.")} />
      <ActionButton label="Privacy notice (website)" onPress={() => WebBrowser.openBrowserAsync("https://www.pamoja.space/apps/privacy")} />
      {SERVER_SELECTION_ENABLED ? <ActionButton label="Connection settings (preview)" onPress={() => router.push("/server-settings" as never)} /> : null}
      <ActionButton label="Delete AFCON360 account" onPress={() => router.push("/(service)/delete-account" as never)} />
      <ActionButton label="Sign out" onPress={() => Alert.alert("Sign out", "Sign out of AFCON360 on this device?", [{ text: "Cancel", style: "cancel" }, { text: "Sign out", onPress: () => { void signOut(); } }])} />
    </Panel>
    <Text style={{ color: palette.muted, fontSize: 12 }}>Privacy and support: pamoja.space/support</Text>
  </AppScreen>;
}
