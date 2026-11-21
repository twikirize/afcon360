import React, { useEffect, useState } from "react";
import Constants from "expo-constants";
import { Alert, Linking, Text, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { AppScreen, ActionButton, PageHeader, Panel, palette } from "@afcon360/mobile-ui";
import { SERVER_SELECTION_ENABLED, getSelectedApiBaseUrl, normalizePreviewApiBaseUrl } from "../src/services/api";
import { useAuth } from "../src/auth/AuthProvider";
import * as SecureStore from "expo-secure-store";

const PUBLIC_PAMOJA_URL = "https://www.pamoja.space";
const METRO_URL_KEY = "afcon360.user.metro-url";

function isPamojaServerUrl(value: string | null): boolean {
  if (!value) return false;
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase();
    return parsed.protocol === "https:" &&
      (host === "pamoja.space" || host.endsWith(".pamoja.space"));
  } catch {
    return false;
  }
}

export default function ServerSettingsScreen() {
  const router = useRouter();
  const { changeApiServer } = useAuth();
  const [currentUrl, setCurrentUrl] = useState<string | null>(null);
  const [draftUrl, setDraftUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [metroDraft, setMetroDraft] = useState("");

  // The laptop Metro helper injects its current API origin into the Expo
  // runtime manifest. This follows Wi-Fi, either hotspot direction, or USB.
  const runtimeApiBaseUrl = String(
    Constants.expoConfig?.extra?.apiBaseUrl ?? PUBLIC_PAMOJA_URL
  );
  const hasRuntimeLocalApi = runtimeApiBaseUrl.startsWith("http://");
  const isDevelopmentClient = Constants.expoConfig?.extra?.isDevelopmentClient === true;
  const isLivePamojaServer = isPamojaServerUrl(currentUrl);

  useEffect(() => {
    let active = true;
    void getSelectedApiBaseUrl().then(savedUrl => {
      if (!active) return;
      setCurrentUrl(savedUrl);
      setDraftUrl(savedUrl);
    }).catch(() => {
      if (active) Alert.alert("Connection settings unavailable", "AFCON360 could not read the saved server setting.");
    });
    void SecureStore.getItemAsync(METRO_URL_KEY).then(value => {
      if (active) setMetroDraft(value ?? "");
    });
    return () => { active = false; };
  }, []);

  const connectToMetro = async (url = metroDraft) => {
    if (busy) return;
    setBusy(true);
    try {
      let parsed: URL;
      try {
        parsed = new URL(url.trim());
      } catch {
        throw new Error("Enter a complete Metro bundler URL starting with http:// or https://.");
      }
      if (!["http:", "https:"].includes(parsed.protocol)) {
        throw new Error("Use http:// or https:// for the Metro bundler.");
      }
      const metroOrigin = parsed.toString().replace(/\/$/, "");
      await SecureStore.setItemAsync(METRO_URL_KEY, metroOrigin);
      setMetroDraft(metroOrigin);
      const configuredScheme = Constants.expoConfig?.scheme;
      const appScheme = Array.isArray(configuredScheme) ? configuredScheme[0] : configuredScheme || "afcon360-preview";
      const deepLink = appScheme + "://expo-development-client/?url=" + encodeURIComponent(metroOrigin);
      const supported = await Linking.canOpenURL(deepLink);
      if (supported) {
        await Linking.openURL(deepLink);
      } else {
        Alert.alert("Cannot open dev client", "The development client is not installed or the link format changed.");
      }
    } catch (error) {
      Alert.alert("Invalid Metro URL", error instanceof Error ? error.message : "Check the address and try again.");
    } finally {
      setBusy(false);
    }
  };

  const save = async (value = draftUrl) => {
    if (busy) return;
    setBusy(true);
    try {
      const nextBaseUrl = normalizePreviewApiBaseUrl(value);
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      let healthResponse: Response;
      try {
        healthResponse = await fetch(nextBaseUrl + "/api/health/ready", {
          method: "GET",
          headers: { Accept: "application/json" },
          signal: controller.signal
        });
      } catch {
        throw new Error(
          "AFCON360 could not reach a ready server. For Wi-Fi/hotspot, check that the phone and laptop share that network, the laptop API listens on all interfaces, and Windows Firewall permits ports 5000 and 8081. For USB, start the development helper so it can set up ADB reverse."
        );
      } finally {
        clearTimeout(timeout);
      }
      const readiness = await healthResponse.json().catch(() => null) as { status?: string } | null;
      if (!healthResponse.ok || readiness?.status !== "ready") {
        throw new Error(
          "The server responded with HTTP " + healthResponse.status + ", but its database readiness check did not pass. Check the laptop API log and database connection."
        );
      }
      const result = await changeApiServer(nextBaseUrl);
      setCurrentUrl(result.baseUrl);
      setDraftUrl(result.baseUrl);
      if (!result.changed) {
        router.back();
        return;
      }
      const message = result.remoteLogoutConfirmed
        ? "The server has changed. Sign in again using an account that belongs to this development environment."
        : "The server has changed and this device's saved credentials were cleared. The old server could not be contacted to confirm remote session revocation; its session may remain until it expires or is revoked there.";
      Alert.alert("Development connection changed", message, [
        { text: "Continue", onPress: () => router.replace("/login" as never) }
      ]);
    } catch (error) {
      Alert.alert("Could not change server", error instanceof Error ? error.message : "Check the address and try again.");
    } finally {
      setBusy(false);
    }
  };

  if (!SERVER_SELECTION_ENABLED) {
    return <AppScreen><Panel><PageHeader eyebrow="Connection" title="Server selection unavailable." description="This setting is available only in an AFCON360 internal preview build." /><ActionButton label="Back" onPress={() => router.back()} /></Panel></AppScreen>;
  }

  return (
    <AppScreen>
      <PageHeader eyebrow={isLivePamojaServer ? "Pamoja live connection" : "Preview connection"} title="Choose your AFCON360 server." description="Use the laptop development server for local testing, or choose public Pamoja. Switching servers clears this device's saved sign-in credentials and offline account cache." />
      <Panel>
        <Text style={{ color: palette.muted, fontSize: 12, fontWeight: "800" }}>CURRENT SERVER</Text>
        <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "800" }}>
          {currentUrl ? (isLivePamojaServer ? "PUBLIC PAMOJA — LIVE SERVER" : "DEVELOPMENT / PREVIEW SERVER") : "Checking saved server…"}
        </Text>
        <Text selectable style={{ color: palette.ink, fontSize: 14, fontWeight: "700" }}>{currentUrl ?? "Loading saved server…"}</Text>
        {isLivePamojaServer ? (
          <Text style={{ color: palette.muted, lineHeight: 20 }}>
            This app is using the live Pamoja API. Backend changes are served by Pamoja directly. Ordinary live users do not need Metro; compatible mobile screen-code updates use Expo OTA, while native changes require a new app build.
          </Text>
        ) : null}
      </Panel>
      <Panel>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Public Pamoja</Text>
        <Text style={{ color: palette.muted, lineHeight: 20 }}>Connect to the live public website API over HTTPS. Use this only when you intend to test the live environment.</Text>
        <ActionButton label="Use public Pamoja" disabled={busy} onPress={() => { setDraftUrl(PUBLIC_PAMOJA_URL); void save(PUBLIC_PAMOJA_URL); }} />
      </Panel>
      {hasRuntimeLocalApi && (
        <Panel>
          <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Laptop development server</Text>
          <Text style={{ color: palette.muted, lineHeight: 20 }}>The current Metro session supplied this API address. It follows the active Wi-Fi or hotspot connection. In USB mode it uses 127.0.0.1 through ADB reverse.</Text>
          <Text selectable style={{ color: palette.ink, fontSize: 13, fontWeight: "700" }}>{runtimeApiBaseUrl}</Text>
          <ActionButton
            label={busy ? "Checking laptop server…" : "Use server for this development session"}
            disabled={busy}
            onPress={() => { setDraftUrl(runtimeApiBaseUrl); void save(runtimeApiBaseUrl); }}
          />
        </Panel>
      )}
      <Panel>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Enter another preview server</Text>
        <Text style={{ color: palette.muted, lineHeight: 20 }}>For Wi-Fi/hotspot, enter the laptop's private IPv4 address on the adapter the phone is connected to. For USB, enter http://127.0.0.1:5000 after the ADB reverse tunnel is active. Private HTTP is supported only for internal preview testing.</Text>
        <TextInput
          accessibilityLabel="API server address"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          value={draftUrl}
          onChangeText={setDraftUrl}
          placeholder="http://192.168.x.x:5000 or http://127.0.0.1:5000"
          placeholderTextColor={palette.muted}
          editable={!busy}
          style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 12, color: palette.ink, backgroundColor: palette.surface }}
        />
        <ActionButton label={busy ? "Checking server…" : "Test and save server"} disabled={busy || !draftUrl.trim()} onPress={() => void save()} />
      </Panel>
      <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>Security: public and remote servers must use HTTPS. Plain HTTP is limited to private-network preview testing on port 5000 or a local USB ADB tunnel. It is not encrypted over Wi-Fi/hotspot; use trusted test networks and test data only. Never send production credentials or financial information over HTTP.</Text>
      <ActionButton label="Back" disabled={busy} onPress={() => router.back()} />
      {isDevelopmentClient && (
        <Panel>
          <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Metro — developer-only Fast Refresh</Text>
          <Text style={{ color: palette.muted, lineHeight: 20 }}>
            Metro serves in-progress app code from your laptop to this development-client build. It does not collect code from the Pamoja server and is not required by ordinary preview or live users. It remains available here only for internal development, even when this developer app is connected to the live Pamoja API.
          </Text>
          <TextInput
            accessibilityLabel="Metro bundler address"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            value={metroDraft}
            onChangeText={setMetroDraft}
            placeholder="http://laptop-ip:8081 or http://127.0.0.1:8081"
            placeholderTextColor={palette.muted}
            editable={!busy}
            style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 12, color: palette.ink, backgroundColor: palette.surface }}
          />
          <ActionButton label={busy ? "Connecting…" : "Save & Connect to Metro"} disabled={busy || !metroDraft.trim()} onPress={() => void connectToMetro()} />
        </Panel>
      )}
    </AppScreen>
  );
}
