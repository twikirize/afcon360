import React, { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Linking, Platform, Pressable, Share, StyleSheet, Text, View } from "react-native";
import Constants from "expo-constants";
import * as Updates from "expo-updates";
import * as SecureStore from "expo-secure-store";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, palette } from "@afcon360/mobile-ui";
import { SERVER_SELECTION_ENABLED } from "../../src/services/api";

type UpdateStatus = "idle" | "checking" | "downloading" | "ready" | "current" | "error" | "unavailable";

type UpdateHistoryEntry = {
  updateId: string;
  createdAt: string | null;
  runtimeVersion: string | null;
  channel: string | null;
  observedAt: string;
};

type AvailableUpdate = {
  id: string | null;
  createdAt: string | null;
  runtimeVersion: string | null;
};

const UPDATE_HISTORY_KEY = "afcon360.user.update-history.v1";
const MAX_UPDATE_HISTORY = 5;

function isUpdateHistoryEntry(value: unknown): value is UpdateHistoryEntry {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.updateId === "string" && typeof record.observedAt === "string";
}

async function readUpdateHistory(): Promise<UpdateHistoryEntry[]> {
  const raw = await SecureStore.getItemAsync(UPDATE_HISTORY_KEY);
  if (!raw) return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed)) return [];
  return parsed.filter(isUpdateHistoryEntry).slice(0, MAX_UPDATE_HISTORY);
}

async function recordAppliedUpdate(
  entry: Omit<UpdateHistoryEntry, "observedAt">
): Promise<UpdateHistoryEntry[]> {
  const existing = await readUpdateHistory();
  if (existing.some((item) => item.updateId === entry.updateId)) return existing;
  const next: UpdateHistoryEntry[] = [
    { ...entry, observedAt: new Date().toISOString() },
    ...existing,
  ].slice(0, MAX_UPDATE_HISTORY);
  await SecureStore.setItemAsync(UPDATE_HISTORY_KEY, JSON.stringify(next));
  return next;
}

function formatUpdateTime(value: string | null): string {
  if (!value) return "Not reported";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function readManifestSummary(manifest: unknown): AvailableUpdate {
  if (!manifest || typeof manifest !== "object") {
    return { id: null, createdAt: null, runtimeVersion: null };
  }
  const record = manifest as Record<string, unknown>;
  return {
    id: typeof record.id === "string" ? record.id : null,
    createdAt: typeof record.createdAt === "string" ? record.createdAt : null,
    runtimeVersion: typeof record.runtimeVersion === "string" ? record.runtimeVersion : null,
  };
}

function InfoRow({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <View style={{ gap: 2 }}>
      <Text style={{ color: palette.muted, fontSize: 12 }}>{label}</Text>
      <Text selectable style={{ color: palette.ink, fontSize: 12, fontWeight: "800", lineHeight: 17 }}>
        {value}
      </Text>
      {hint ? <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 16 }}>{hint}</Text> : null}
    </View>
  );
}

function AppUpdateControls() {
  const [status, setStatus] = useState<UpdateStatus>("idle");
  const [message, setMessage] = useState(
    "AFCON360 checks for compatible updates when the app starts. You can also check manually here."
  );

  const [history, setHistory] = useState<UpdateHistoryEntry[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null);
  const [availableUpdate, setAvailableUpdate] = useState<AvailableUpdate | null>(null);

  const appVersion = Constants.expoConfig?.version ?? "Unknown";
  const runtimeVersion = Updates.runtimeVersion ?? "Not reported";
  const channel = Updates.channel ?? "Not configured";
  const runningUpdateId = Updates.updateId;
  const runningUpdateCreatedAt = Updates.createdAt ? Updates.createdAt.toISOString() : null;
  const bundleSource = Updates.isEmbeddedLaunch ? "Embedded app bundle" : "Downloaded OTA update";
  const busy = status === "checking" || status === "downloading";

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const entries = await readUpdateHistory();
        if (!cancelled) setHistory(entries);
        if (runningUpdateId) {
          const next = await recordAppliedUpdate({
            updateId: runningUpdateId,
            createdAt: runningUpdateCreatedAt,
            runtimeVersion: Updates.runtimeVersion,
            channel: Updates.channel,
          });
          if (!cancelled) setHistory(next);
        }
      } catch {
        if (!cancelled) setHistoryError("Update history is unavailable on this installation.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runningUpdateId, runningUpdateCreatedAt]);

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
      setLastCheckedAt(new Date().toISOString());

      if (check.isRollBackToEmbedded) {
        setAvailableUpdate(null);
        setStatus("ready");
        setMessage(
          "A verified rollback to the embedded app version is available. Restart AFCON360 to apply it."
        );
        return;
      }

      if (!check.isAvailable) {
        setAvailableUpdate(null);
        setStatus("current");
        setMessage(
          "This app is up to date. AFCON360 will continue checking automatically when it starts."
        );
        return;
      }

      setAvailableUpdate(readManifestSummary(check.manifest));
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
          Method 1 · Compatible app updates
        </Text>
        <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 16 }}>
          Receive compatible JavaScript and asset improvements over the air. Changes to native code, permissions or SDKs require a full app update using Method 2 below.
        </Text>
      </View>

      <InfoRow label="Installed version" value={appVersion} hint="Version reported by this installation" />
      <InfoRow label="Compatible runtime" value={runtimeVersion} hint="OTA updates must match this runtime version" />
      <InfoRow label="Update channel" value={channel} />
      <InfoRow
        label="Running update"
        value={runningUpdateId ?? "Built-in app bundle"}
        hint={bundleSource + (runningUpdateCreatedAt ? " · created " + formatUpdateTime(runningUpdateCreatedAt) : "")}
      />
      <InfoRow
        label="Latest update found"
        value={availableUpdate?.id ?? (lastCheckedAt ? "No newer compatible update" : "Not checked yet")}
        hint={
          availableUpdate?.createdAt
            ? "created " + formatUpdateTime(availableUpdate.createdAt)
            : lastCheckedAt
              ? "Checked " + formatUpdateTime(lastCheckedAt)
              : "Tap Check for updates below"
        }
      />
      <InfoRow
        label="Last checked"
        value={lastCheckedAt ? formatUpdateTime(lastCheckedAt) : "Not checked in this session"}
      />

      <View style={{ gap: 4, borderTopWidth: 1, borderTopColor: palette.border, paddingTop: 10 }}>
        <Text style={{ color: palette.ink, fontSize: 12, fontWeight: "900" }}>Applied update sequence</Text>
        {historyError ? (
          <Text style={{ color: "#A12E27", fontSize: 11, lineHeight: 16 }}>{historyError}</Text>
        ) : history.length === 0 ? (
          <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 16 }}>
            No OTA update has been recorded yet. After an update is applied and the app restarts, it will appear here.
          </Text>
        ) : (
          history.map((entry, index) => (
            <View key={entry.updateId} style={{ gap: 1 }}>
              <Text selectable style={{ color: palette.ink, fontSize: 11, fontWeight: "800" }}>
                {index + 1}. {entry.updateId}
                {entry.updateId === runningUpdateId ? "  · running now" : ""}
              </Text>
              <Text style={{ color: palette.muted, fontSize: 10 }}>
                created {formatUpdateTime(entry.createdAt)} · observed {formatUpdateTime(entry.observedAt)}
              </Text>
            </View>
          ))
        )}
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

  const openNativeAppUpdate = async () => {
    const officialDownloadsUrl = "https://www.pamoja.space/download";
    try {
      await Linking.openURL(officialDownloadsUrl);
    } catch {
      try {
        await WebBrowser.openBrowserAsync(officialDownloadsUrl);
      } catch {
        Alert.alert(
          "Update page unavailable",
          "AFCON360 could not open the official downloads page. Open this address in your browser: " +
            officialDownloadsUrl
        );
      }
    }
  };

  const nativeUpdateDescription =
    "Use Pamoja's official downloads page for full Android and iOS releases. Official store links appear when configured; any pre-Play Android APKs are clearly labelled as internal previews. Android requires user confirmation before an APK can be installed.";

  const nativeUpdateActionLabel = "Open official downloads";

  const shareApp = async () => {
    const url = "https://www.pamoja.space/download";
    try {
      await Share.share({ message: "AFCON360 — official app information and downloads. " + url, url });
    } catch {
      Alert.alert("Share unavailable", "Copy this link: " + url);
    }
  };

  const openAndroidUninstallSettings = async () => {
    try {
      // Android owns the package removal and final system confirmation.
      // AFCON360 never attempts to remove its own package programmatically.
      await Linking.openSettings();
    } catch {
      Alert.alert(
        "Android app settings unavailable",
        "Open Android Settings, choose Apps, select AFCON360, then choose Uninstall. Android will ask you to confirm."
      );
    }
  };

  const requestUninstall = () => {
    if (Platform.OS !== "android") {
      Alert.alert(
        "Remove AFCON360",
        "On iPhone or iPad, remove AFCON360 from the Home Screen or from Settings > General > iPhone Storage."
      );
      return;
    }

    Alert.alert(
      "Uninstall AFCON360?",
      "This removes AFCON360 and its saved offline information from this phone. Your AFCON360 account and server-held wallet records, bookings, tickets and transactions remain on AFCON360. You can restore them by reinstalling and signing in. Continue to Android's app settings, where Android will ask you to confirm the uninstall.",
      [
        { text: "Keep AFCON360", style: "cancel" },
        { text: "Continue to Android settings", style: "destructive", onPress: () => void openAndroidUninstallSettings() }
      ]
    );
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
      </Panel>
      <Panel>
        <SectionTitle>Method 2 · Full app update</SectionTitle>
        <Text style={styles.sectionHint}>
          Use this route when an update needs a new native Android or iOS binary, such as native code, permissions, SDK or dependency changes. This is separate from OTA updates and always hands installation to the official store or Android system installer for user confirmation.
        </Text>
        <View style={styles.actionRow}>
          <View style={styles.actionIcon}>
            <Text style={styles.actionIconText}>⬆</Text>
          </View>
          <View style={styles.actionCopy}>
            <Text style={styles.actionTitle}>
              "Official app distribution"
            </Text>
            <Text style={styles.actionDescription}>{nativeUpdateDescription}</Text>
          </View>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={nativeUpdateActionLabel}
          onPress={() => void openNativeAppUpdate()}
          style={[styles.actionRow, { justifyContent: "center", backgroundColor: "#E7F1E9", borderRadius: 11, borderTopWidth: 0, paddingHorizontal: 12 }]}
        >
          <Text style={{ color: "#175D37", fontSize: 12, fontWeight: "900" }}>
            {nativeUpdateActionLabel} ↗
          </Text>
        </Pressable>
      </Panel>
      <Panel>
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

      {Platform.OS === "android" ? (
        <Panel>
          <SectionTitle>Remove from this phone</SectionTitle>
          <Text style={styles.sectionHint}>
            Choose this only when you deliberately want to remove AFCON360 from this device. Your online account and server records are not deleted.
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Uninstall AFCON360 from this device"
            onPress={requestUninstall}
            style={styles.dangerButton}
          >
            <Text style={styles.dangerButtonText}>Uninstall AFCON360 from this device</Text>
          </Pressable>
          <Text style={styles.sectionHint}>
            AFCON360 asks first. Android then opens its own app settings and requires you to choose Uninstall and confirm there. You can cancel either step.
          </Text>
        </Panel>
      ) : null}

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
  dangerButton: {
    minHeight: 46,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 11,
    borderWidth: 1,
    borderColor: "#E8B8B2",
    backgroundColor: "#FFF1EF",
    paddingHorizontal: 14,
    paddingVertical: 11
  },
  dangerButtonText: { color: "#9A332B", fontSize: 12, fontWeight: "900" },
  footer: { color: palette.muted, textAlign: "center", fontSize: 10, paddingBottom: 4 }
});
