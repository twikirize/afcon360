import React, { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Linking, Text, TextInput, View } from "react-native";
import Constants from "expo-constants";
import { useRouter } from "expo-router";
import * as SecureStore from "expo-secure-store";
import { AppScreen, ActionButton, PageHeader, Panel, palette } from "@afcon360/mobile-ui";

const METRO_URL_KEY = "afcon360.user.metro-url";
const METRO_LAST_SUCCESS_KEY = "afcon360.user.metro-last-success";
const LAPTOP_IP_KEY = "afcon360.user.laptop-ip";
const LISTENER_PORT = 8082;
const METRO_DEFAULT_PORT = 8081;

type HealthResponse = {
  status: "running" | "starting" | "stopped" | "error" | "unknown";
  port: number;
  message?: string;
  updatedAt?: number;
};

export default function ConnectionScreen() {
  const router = useRouter();
  const [metroUrl, setMetroUrl] = useState("");
  const [laptopIp, setLaptopIp] = useState("");
  const [lastSuccess, setLastSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [waking, setWaking] = useState(false);
  const [polling, setPolling] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "connecting" | "connected" | "error">("idle");
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let active = true;
    SecureStore.getItemAsync(METRO_URL_KEY).then(value => {
      if (active && value) setMetroUrl(value);
    });
    SecureStore.getItemAsync(METRO_LAST_SUCCESS_KEY).then(value => {
      if (active && value) setLastSuccess(value);
    });
    SecureStore.getItemAsync(LAPTOP_IP_KEY).then(value => {
      if (active && value) setLaptopIp(value);
    });
    return () => { active = false; };
  }, []);

  const connectToMetro = useCallback(async (url = metroUrl) => {
    if (busy) return;
    setBusy(true);
    setStatus("connecting");
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
      setMetroUrl(metroOrigin);
      const configuredScheme = Constants.expoConfig?.scheme;
      const appScheme = Array.isArray(configuredScheme) ? configuredScheme[0] : configuredScheme || "afcon360-preview";
      const deepLink = appScheme + "://expo-development-client/?url=" + encodeURIComponent(metroOrigin);
      const supported = await Linking.canOpenURL(deepLink);
      if (supported) {
        await Linking.openURL(deepLink);
        await SecureStore.setItemAsync(METRO_LAST_SUCCESS_KEY, metroOrigin);
        setLastSuccess(metroOrigin);
        setStatus("connected");
        Alert.alert("Metro connected", "The development client is now connected to Metro. Fast Refresh is active.");
      } else {
        throw new Error("Cannot open dev client. The development client is not installed or the link format changed.");
      }
    } catch (error) {
      setStatus("error");
      Alert.alert("Connection failed", error instanceof Error ? error.message : "Check the address and try again.");
    } finally {
      setBusy(false);
    }
  }, [busy, metroUrl]);

  const fetchHealth = useCallback(async () => {
    if (!laptopIp.trim()) return;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      const response = await fetch(`http://${laptopIp}:${LISTENER_PORT}/health`, {
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (response.ok) {
        const data = await response.json() as HealthResponse;
        setHealth(data);
        return data;
      }
    } catch {
      // ignore
    }
    return null;
  }, [laptopIp]);

  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    setPolling(true);
    pollIntervalRef.current = setInterval(async () => {
      const data = await fetchHealth();
      if (data && data.status === "running") {
        stopPolling();
        const metroUrl = `http://${laptopIp}:${data.port}`;
        setMetroUrl(metroUrl);
        setStatus("idle");
        Alert.alert("Metro ready", `Metro is running on port ${data.port}. Tap "Use this address" to connect.`);
      } else if (data && data.status === "error") {
        stopPolling();
        Alert.alert("Metro error", data.message || "Failed to start Metro.");
      }
    }, 3000);
  }, [fetchHealth, laptopIp]);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    setPolling(false);
  }, []);

  const wakeMetro = useCallback(async () => {
    if (waking || !laptopIp.trim()) return;
    setWaking(true);
    setHealth(null);
    setStatus("idle");
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      const response = await fetch(`http://${laptopIp}:${LISTENER_PORT}/wake`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId: Constants.installationId, timestamp: Date.now() }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!response.ok) throw new Error(`Listener responded with ${response.status}`);
      const data = await response.json();
      if (data.status === "triggered") {
        startPolling();
      } else {
        throw new Error("Unexpected listener response");
      }
    } catch (error) {
      setStatus("error");
      Alert.alert("Wake failed", error instanceof Error ? error.message : "Could not reach laptop listener. Check IP and ensure listener is running.");
    } finally {
      setWaking(false);
    }
  }, [waking, laptopIp, startPolling]);

  const saveLaptopIp = useCallback(async (ip: string) => {
    await SecureStore.setItemAsync(LAPTOP_IP_KEY, ip);
    setLaptopIp(ip);
  }, []);

  const isDevClient = Constants.expoConfig?.scheme === "afcon360-preview-dev" ||
    (Array.isArray(Constants.expoConfig?.scheme) && Constants.expoConfig?.scheme.includes("afcon360-preview-dev"));

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  return (
    <AppScreen>
      <PageHeader
        eyebrow={isDevClient ? "Developer connection" : "Preview connection"}
        title="Metro — Fast Refresh"
        description={isDevClient
          ? "Connect to the Metro bundler on your laptop for live code updates. This screen is also available from the hidden developer menu (5× tap the logo on Account)."
          : "This preview build includes an embedded bundle. Connect to Metro to enable Fast Refresh during development."}
      />
      <Panel>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Current Metro URL</Text>
        <Text selectable style={{ color: palette.muted, fontSize: 13, fontFamily: "monospace" }}>
          {metroUrl || "Not configured"}
        </Text>
      </Panel>
      {lastSuccess && (
        <Panel>
          <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Last successful connection</Text>
          <Text selectable style={{ color: palette.green, fontSize: 13, fontFamily: "monospace" }}>{lastSuccess}</Text>
          <ActionButton label="Reuse last" disabled={busy} onPress={() => { setMetroUrl(lastSuccess); void connectToMetro(lastSuccess); }} />
        </Panel>
      )}
      <Panel>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Laptop IP (for auto-wake)</Text>
        <Text style={{ color: palette.muted, lineHeight: 20, marginBottom: 8 }}>
          Enter your laptop's private IP on the shared network (Wi-Fi/hotspot). For USB with ADB reverse, use <Text style={{ fontFamily: "monospace" }}>127.0.0.1</Text>. This calls the listener on port {LISTENER_PORT}.
        </Text>
        <TextInput
          accessibilityLabel="Laptop IP address"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="numbers-and-punctuation"
          value={laptopIp}
          onChangeText={setLaptopIp}
          placeholder="192.168.x.x or 127.0.0.1"
          placeholderTextColor={palette.muted}
          editable={!busy}
          style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 12, color: palette.ink, backgroundColor: palette.surface }}
        />
        <ActionButton label="Save laptop IP" disabled={busy || !laptopIp.trim()} onPress={() => void saveLaptopIp(laptopIp)} />
      </Panel>
      <Panel>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Auto-wake Metro</Text>
        <Text style={{ color: palette.muted, lineHeight: 20, marginBottom: 8 }}>
          Calls the laptop listener at <Text style={{ fontFamily: "monospace" }}>http://{laptopIp || "laptop-ip"}:{LISTENER_PORT}/wake</Text>.
          The listener writes a trigger; the Metro Manager (running on laptop) starts Metro and updates status.
        </Text>
        <ActionButton
          label={waking ? "Triggering…" : polling ? "Waiting for Metro…" : "Wake Metro on Laptop"}
          disabled={busy || waking || polling || !laptopIp.trim()}
          onPress={() => void wakeMetro()}
        />
        {polling && health && (
          <View style={{ marginTop: 12, gap: 8 }}>
            <Text style={{ color: palette.ink, fontWeight: "800" }}>
              Metro status: {health.status} — {health.message}
            </Text>
            <ActionButton label="Stop waiting" onPress={stopPolling} />
          </View>
        )}
        {health && health.status === "running" && !polling && (
          <View style={{ marginTop: 12, gap: 8 }}>
            <Text style={{ color: palette.green, fontWeight: "800" }}>
              Metro is running on port {health.port}
            </Text>
            <ActionButton label="Use this Metro address" onPress={() => {
              const url = `http://${laptopIp}:${health.port}`;
              setMetroUrl(url);
            }} />
          </View>
        )}
      </Panel>
      <Panel>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>Manual Metro address</Text>
        <Text style={{ color: palette.muted, lineHeight: 20, marginBottom: 8 }}>
          Enter the laptop's Metro bundler address directly. For USB with ADB reverse: <Text style={{ fontFamily: "monospace" }}>http://127.0.0.1:8081</Text>. For Wi-Fi/hotspot: <Text style={{ fontFamily: "monospace" }}>http://192.168.x.x:8081</Text>.
        </Text>
        <TextInput
          accessibilityLabel="Metro bundler address"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          value={metroUrl}
          onChangeText={setMetroUrl}
          placeholder="http://laptop-ip:8081"
          placeholderTextColor={palette.muted}
          editable={!busy}
          style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 12, color: palette.ink, backgroundColor: palette.surface }}
        />
        <ActionButton label={busy ? "Connecting…" : "Save & Connect to Metro"} disabled={busy || !metroUrl.trim()} onPress={() => void connectToMetro()} />
      </Panel>
      <Panel>
        <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>
          The laptop listener (<Text style={{ fontFamily: "monospace" }}>python metro_listener.py</Text>) must be running on port {LISTENER_PORT}.
          The Metro Manager (<Text style={{ fontFamily: "monospace" }}>python metro_manager.py</Text>) watches for triggers and starts Metro in a new console window.
          Both scripts run on your development laptop.
        </Text>
      </Panel>
      <ActionButton label="Back" disabled={busy} onPress={() => router.back()} />
    </AppScreen>
  );
}