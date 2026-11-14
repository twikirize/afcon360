import React, { useState } from "react";
import { ActivityIndicator, Alert, Pressable, Share, StyleSheet, Text, View } from "react-native";
import Constants from "expo-constants";
import * as Updates from "expo-updates";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, palette } from "@afcon360/mobile-ui";
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

export default function UserAppSettings() {
  const router = useRouter();
  const appVersion = Constants.expoConfig?.version ?? "Unknown";

  const shareApp = async () => {
    const url = "https://www.pamoja.space/apps";
    try {
      await Share.share({ message: "AFCON360 — official app information and downloads. " + url, url });
    } catch {
      Alert.alert("Share unavailable", "Copy this link: " + url);
    }
  };

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Settings"
        title="App settings."
        description="Manage this installation of AFCON360, its version and connection."
      />

      <Panel>
        <SectionTitle>Version & updates</SectionTitle>
        <View style={styles.versionHero}>
          <View style={styles.versionIcon}>
            <Text style={styles.versionIconText}>360</Text>
          </View>
          <View style={styles.versionCopy}>
            <Text style={styles.versionName}>AFCON360 User</Text>
            <Text style={styles.versionNumber}>Version {appVersion}</Text>
          </View>
        </View>
        <Text style={styles.sectionHint}>
          Check for a compatible AFCON360 update. Updates are downloaded securely and applied when you restart the app.
        </Text>
        <AppUpdateControls />
      </Panel>      <Panel>
        <SectionTitle>Connection</SectionTitle>
        <Text style={styles.sectionHint}>
          Manage which AFCON360 server this app connects to. This option appears only in preview installations.
        </Text>
        {SERVER_SELECTION_ENABLED ? (
          <Pressable
            accessibilityRole="button"
            onPress={() => router.push("/server-settings" as never)}
            style={styles.actionRow}
          >
            <View style={styles.actionIcon}><Text style={styles.actionIconText}>⇄</Text></View>
            <View style={styles.actionCopy}>
              <Text style={styles.actionTitle}>Connection settings</Text>
              <Text style={styles.actionDescription}>Choose the preview server used by this app</Text>
            </View>
            <Text style={styles.actionArrow}>›</Text>
          </Pressable>
        ) : (
          <Text style={styles.sectionHint}>The connection is managed by this installation.</Text>
        )}
        <Pressable accessibilityRole="button" onPress={() => void shareApp()} style={styles.actionRow}>
          <View style={styles.actionIcon}><Text style={styles.actionIconText}>↗</Text></View>
          <View style={styles.actionCopy}>
            <Text style={styles.actionTitle}>Share AFCON360</Text>
            <Text style={styles.actionDescription}>Share the official app information and download page</Text>
          </View>
          <Text style={styles.actionArrow}>›</Text>
        </Pressable>
      </Panel>

      <Text style={styles.footer}>AFCON360 · App version and installation settings.</Text>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  versionHero: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 13,
    borderRadius: 14,
    backgroundColor: "#F1F6F2",
    marginBottom: 6
  },
  versionIcon: {
    width: 48,
    height: 48,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#173D28"
  },
  versionIconText: { color: "#FFCC00", fontSize: 14, fontWeight: "900" },
  versionCopy: { flex: 1, gap: 3 },
  versionName: { color: palette.ink, fontSize: 13, fontWeight: "900" },
  versionNumber: { color: palette.muted, fontSize: 11 },
  metaRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    paddingVertical: 9,
    borderTopWidth: 1,
    borderTopColor: palette.border
  },
  metaLabel: { color: palette.muted, fontSize: 11 },
  metaValue: { color: palette.ink, fontSize: 11, fontWeight: "800", textAlign: "right", flexShrink: 1 },
  sectionHint: { color: palette.muted, fontSize: 11, lineHeight: 17 },
  actionRow: {
    minHeight: 66,
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: palette.border
  },
  actionIcon: {
    width: 38,
    height: 38,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#E7F1E9"
  },
  actionIconText: { color: "#175D37", fontSize: 19, fontWeight: "800" },
  actionCopy: { flex: 1, gap: 3 },
  actionTitle: { color: palette.ink, fontSize: 12, fontWeight: "900" },
  actionDescription: { color: palette.muted, fontSize: 10, lineHeight: 15 },
  actionArrow: { color: palette.muted, fontSize: 21, fontWeight: "700" },
  footer: { color: palette.muted, textAlign: "center", fontSize: 10, paddingBottom: 4 }
});
