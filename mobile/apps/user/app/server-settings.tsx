import React, { useEffect, useState } from "react";
import { Alert, Text, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { AppScreen, ActionButton, PageHeader, Panel, palette } from "@afcon360/mobile-ui";
import { SERVER_SELECTION_ENABLED, getSelectedApiBaseUrl, normalizePreviewApiBaseUrl } from "../src/services/api";
import { useAuth } from "../src/auth/AuthProvider";

const PUBLIC_PAMOJA_URL = "https://www.pamoja.space";

export default function ServerSettingsScreen() {
  const router = useRouter();
  const { changeApiServer } = useAuth();
  const [currentUrl, setCurrentUrl] = useState<string | null>(null);
  const [draftUrl, setDraftUrl] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    void getSelectedApiBaseUrl().then(value => {
      if (active) {
        setCurrentUrl(value);
        setDraftUrl(value);
      }
    }).catch(() => {
      if (active) Alert.alert("Connection settings unavailable", "AFCON360 could not read the saved server setting.");
    });
    return () => { active = false; };
  }, []);

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
    </AppScreen>
  );
}
