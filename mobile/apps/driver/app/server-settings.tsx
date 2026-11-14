import React, { useEffect, useState } from "react";
import { Alert, Text, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { ActionButton, AppScreen, PageHeader, Panel, palette } from "@afcon360/mobile-ui";
import { SERVER_SELECTION_ENABLED, getSelectedApiBaseUrl } from "../src/services/api";
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
      if (active) Alert.alert("Connection settings unavailable", "AFCON360 Driver could not read the saved server setting.");
    });
    return () => { active = false; };
  }, []);

  const save = async (value = draftUrl) => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await changeApiServer(value);
      setCurrentUrl(result.baseUrl);
      setDraftUrl(result.baseUrl);
      if (!result.changed) {
        router.back();
        return;
      }
      const message = result.remoteLogoutConfirmed
        ? "The server has changed. Sign in again using a test Driver account that belongs to this environment."
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
    return (
      <AppScreen>
        <Panel>
          <PageHeader eyebrow="Connection" title="Server selection unavailable." description="This setting is available only in an AFCON360 internal Driver preview build." />
          <ActionButton label="Back" onPress={() => router.back()} />
        </Panel>
      </AppScreen>
    );
  }

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Driver preview connection"
        title="Choose your AFCON360 server."
        description="Connect this preview app to laptop staging over Wi-Fi, or return to the public Pamoja server. Switching servers clears this device's saved sign-in credentials."
      />
      <Panel>
        <Text style={{ color: palette.muted, fontSize: 12, fontWeight: "800" }}>CURRENT SERVER</Text>
        <Text selectable style={{ color: palette.ink, fontSize: 14, fontWeight: "700" }}>{currentUrl ?? "Loading saved server…"}</Text>
      </Panel>
      <Panel>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Public Pamoja</Text>
        <Text style={{ color: palette.muted, lineHeight: 20 }}>Connect to the live public API over HTTPS. Use this only when you intend to test the live environment.</Text>
        <ActionButton label="Use public Pamoja" disabled={busy} onPress={() => { setDraftUrl(PUBLIC_PAMOJA_URL); void save(PUBLIC_PAMOJA_URL); }} />
      </Panel>
      <Panel>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Another trusted server</Text>
        <Text style={{ color: palette.muted, lineHeight: 20 }}>
          For laptop Wi-Fi or phone-hotspot staging, enter the exact laptop IPv4 address printed by the staging runner. Use the laptop's IP, not the phone's hotspot gateway. Example format: http://192.168.60.214:5000
        </Text>
        <TextInput
          accessibilityLabel="API server address"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          value={draftUrl}
          onChangeText={setDraftUrl}
          placeholder="http://<LAPTOP-IP>:5000"
          placeholderTextColor={palette.muted}
          editable={!busy}
          style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 12, color: palette.ink, backgroundColor: palette.surface }}
        />
        <ActionButton label={busy ? "Changing server…" : "Save server address"} disabled={busy || !draftUrl.trim()} onPress={() => void save()} />
      </Panel>
      <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>
        Security: public servers must use HTTPS. Plain HTTP is restricted to private IPv4 staging addresses on port 5000 in this preview app. Never select an untrusted server. Use a synthetic test account for laptop staging; changing server clears locally saved credentials.
      </Text>
      <ActionButton label="Back" disabled={busy} onPress={() => router.back()} />
    </AppScreen>
  );
}
