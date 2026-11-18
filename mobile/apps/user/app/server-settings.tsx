import React, { useEffect, useState } from "react";
import { Alert, Linking, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { AppScreen, ActionButton, PageHeader, Panel, palette } from "@afcon360/mobile-ui";
import { SERVER_SELECTION_ENABLED, getSelectedApiBaseUrl, normalizePreviewApiBaseUrl } from "../src/services/api";
import { useAuth } from "../src/auth/AuthProvider";
import * as SecureStore from "expo-secure-store";

const PUBLIC_PAMOJA_URL = "https://www.pamoja.space";
const METRO_URL_KEY = "afcon360.user.metro-url";
const DEFAULT_METRO_URL = "http://192.168.100.28:8081";

export default function ServerSettingsScreen() {
  const router = useRouter();
  const { changeApiServer } = useAuth();
  const [currentUrl, setCurrentUrl] = useState<string | null>(null);
  const [draftUrl, setDraftUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [metroUrl, setMetroUrl] = useState<string | null>(null);
  const [metroDraft, setMetroDraft] = useState("");
  const [serverUrls, setServerUrls] = useState<{ api_base_urls: string[]; metro_urls: string[] } | null>(null);

  useEffect(() => {
    let active = true;
    void getSelectedApiBaseUrl().then(savedUrl => {
      if (!active) return;
      setCurrentUrl(savedUrl);
      setDraftUrl(savedUrl);
      // Auto-fetch current server URLs using the saved URL as base
      fetch(`${savedUrl}/api/health/server-urls`)
        .then(r => r.json())
        .then(data => {
          if (!active) return;
          if (data?.api_base_urls?.length) {
            setServerUrls(data);
            if (!savedUrl) setDraftUrl(data.api_base_urls[0]);
            if (!metroDraft) setMetroDraft(data.metro_urls?.[0] ?? "");
          }
        })
        .catch(() => {});
    }).catch(() => {
      if (active) Alert.alert("Connection settings unavailable", "AFCON360 could not read the saved server setting.");
    });
    void SecureStore.getItemAsync(METRO_URL_KEY).then(value => {
      if (active) {
        const url = value ?? "";
        setMetroUrl(url);
        setMetroDraft(url);
      }
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
      await SecureStore.setItemAsync(METRO_URL_KEY, parsed.toString().replace(/\/$/, ""));
      setMetroUrl(parsed.toString().replace(/\/$/, ""));
      setMetroDraft(parsed.toString().replace(/\/$/, ""));
      const deepLink = `afcon360-preview://expo-development-client/?url=${encodeURIComponent(parsed.toString().replace(/\/$/, ""))}`;
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
        healthResponse = await fetch(nextBaseUrl + "/api/health/ping", {
          method: "GET",
          headers: { Accept: "application/json" },
          signal: controller.signal
        });
      } catch {
        throw new Error(
          "AFCON360 could not reach this server. Check the laptop IP, confirm the phone and laptop are on the same hotspot or Wi-Fi, and make sure the API and firewall allow port 5000."
        );
      } finally {
        clearTimeout(timeout);
      }
      if (!healthResponse.ok) {
        throw new Error(
          `The server responded with HTTP ${healthResponse.status}, but its AFCON360 health check did not pass.`
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
        ? "The server has changed. Sign in again using an account that belongs to this environment."
        : "The server has changed and this device's saved credentials were cleared. The old server could not be contacted to confirm remote session revocation; its session may remain until it expires or is revoked there.";
      Alert.alert("Connection changed", message, [
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
      <PageHeader eyebrow="Preview connection" title="Choose your AFCON360 server." description="Choose public Pamoja or enter the server reachable on your current network. Switching servers clears this device's saved sign-in credentials." />
      <Panel>
        <Text style={{ color: palette.muted, fontSize: 12, fontWeight: "800" }}>CURRENT SERVER</Text>
        <Text selectable style={{ color: palette.ink, fontSize: 14, fontWeight: "700" }}>{currentUrl ?? "Loading saved server…"}</Text>
      </Panel>
      <Panel>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Public Pamoja</Text>
        <Text style={{ color: palette.muted, lineHeight: 20 }}>Connect to the live public website API over HTTPS. Use this only when you intend to test the live environment.</Text>
        <ActionButton label="Use public Pamoja" disabled={busy} onPress={() => { setDraftUrl(PUBLIC_PAMOJA_URL); void save(PUBLIC_PAMOJA_URL); }} />
      </Panel>
      {serverUrls?.api_base_urls && serverUrls.api_base_urls.length > 1 && (
        <Panel>
          <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Auto-detected laptop servers</Text>
          <Text style={{ color: palette.muted, lineHeight: 20, marginBottom: 8 }}>These are the current IPs your laptop is reachable on. Tap one to test & save instantly.</Text>
          {serverUrls.api_base_urls.map((url, i) => (
            <View key={i} style={{ marginBottom: 6 }}>
              <ActionButton
                label={`Use ${url}`}
                disabled={busy}
                onPress={() => { setDraftUrl(url); void save(url); }}
              />
            </View>
          ))}
        </Panel>
      )}
      <Panel>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Laptop hotspot or another staging server</Text>
        <Text style={{ color: palette.muted, lineHeight: 20 }}>For laptop testing, enter the laptop's current private IPv4 address on the Wi-Fi or hotspot adapter. The phone and laptop must be on the same local network. Example only: http://192.168.137.1:5000. Replace that address with the one shown by ipconfig on your laptop.</Text>
        <TextInput
          accessibilityLabel="API server address"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          value={draftUrl}
          onChangeText={setDraftUrl}
          placeholder="http://192.168.x.x:5000 or https://staging.example"
          placeholderTextColor={palette.muted}
          editable={!busy}
          style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 12, color: palette.ink, backgroundColor: palette.surface }}
        />
        <ActionButton label={busy ? "Checking server…" : "Test and save server"} disabled={busy || !draftUrl.trim()} onPress={() => void save()} />
      </Panel>
      <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>Security: public and remote servers must use HTTPS. Plain HTTP is allowed only for private-network preview testing on port 5000; it is not encrypted. Use it only on a trusted, isolated test network with test data. Never send production credentials or financial information over HTTP.</Text>
      <ActionButton label="Back" disabled={busy} onPress={() => router.back()} />
      <Panel>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Metro Bundler (Fast Refresh)</Text>
        <Text style={{ color: palette.muted, lineHeight: 20 }}>Enter the laptop's Metro bundler address for wireless Fast Refresh. The phone and laptop must be on the same hotspot or Wi-Fi. Example: http://10.247.255.214:8081. Restart Metro with </Text>
        <Text style={{ color: palette.muted, lineHeight: 20, fontFamily: "monospace" }}>npx expo start --dev-client --host lan --port 8081</Text>
        <Text style={{ color: palette.muted, lineHeight: 20 }}> on the laptop.</Text>
        <TextInput
          accessibilityLabel="Metro bundler address"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          value={metroDraft}
          onChangeText={setMetroDraft}
          placeholder="http://10.247.255.214:8081"
          placeholderTextColor={palette.muted}
          editable={!busy}
          style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 12, color: palette.ink, backgroundColor: palette.surface }}
        />
        <ActionButton label={busy ? "Connecting…" : "Save & Connect to Metro"} disabled={busy || !metroDraft.trim()} onPress={() => void connectToMetro()} />
      </Panel>
    </AppScreen>
  );
}
