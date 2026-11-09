import React, { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Share, Text, View } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { useFocusEffect, useRouter } from "expo-router";
import {
  ActionButton,
  AppScreen,
  EmptyState,
  PageHeader,
  Panel,
  SectionTitle,
  StatusPill,
  palette
} from "@afcon360/mobile-ui";
import { useAuth } from "../../src/auth/AuthProvider";
import { authClient } from "../../src/services/api";

type ReadinessCheck = {
  key: string;
  label: string;
  ok: boolean;
  required: boolean;
  hint?: string;
};

type DriverProfileSummary = {
  driver_code: string;
  verification_tier: string;
  compliance_status: string;
  is_online: boolean;
  is_available: boolean;
  go_live: {
    ready: boolean;
    checks: ReadinessCheck[];
  };
};

function AccountValue({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1, minWidth: 125, gap: 3 }}>
      <Text style={{ color: palette.muted, fontSize: 11, fontWeight: "700" }}>{label}</Text>
      <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "800" }}>{value}</Text>
    </View>
  );
}

export default function DriverAccount() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [profile, setProfile] = useState<DriverProfileSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await authClient.request<{ data: DriverProfileSummary }>(
        "/api/mobile/v1/driver/me"
      );
      setProfile(response.data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Driver approval and readiness could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
  );

  const share = async (url: string, message: string) => {
    try {
      await Share.share({ message: message + " " + url, url });
    } catch {
      Alert.alert("Share unavailable", "Copy this link: " + url);
    }
  };

  const signOut = () => {
    Alert.alert("Sign out", "Sign out this driver device?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Sign out",
        onPress: () => {
          void logout()
            .then(() => router.replace("/login"))
            .catch(() => router.replace("/login"));
        }
      }
    ]);
  };

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Driver account"
        title="Your AFCON360 identity."
        description="Review your server-verified driver status and the requirements for going online."
      />

      <Panel>
        <StatusPill tone="green">Signed in securely</StatusPill>
        <SectionTitle>{user?.display_name ?? user?.username ?? "Driver account"}</SectionTitle>
        <Text style={{ color: palette.muted, fontSize: 12 }}>{user?.email ?? ""}</Text>
      </Panel>

      <Panel>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <SectionTitle>Driver approval and readiness</SectionTitle>
          {profile ? (
            <StatusPill tone={profile.go_live?.ready ? "green" : "gold"}>
              {profile.go_live?.ready ? "Ready to go live" : "Not ready"}
            </StatusPill>
          ) : null}
        </View>

        {loading && !profile ? <ActivityIndicator color={palette.green} /> : null}
        {error ? (
          <View style={{ gap: 8 }}>
            <Text accessibilityRole="alert" style={{ color: "#9A3A2F", fontSize: 13, lineHeight: 19 }}>
              {error}
            </Text>
            <ActionButton
              label={loading ? "Refreshing…" : "Retry driver status"}
              disabled={loading}
              onPress={() => { setLoading(true); void load(); }}
            />
          </View>
        ) : null}

        {profile ? (
          <>
            <Text style={{ color: palette.ink, fontSize: 18, fontWeight: "900" }}>
              Driver {profile.driver_code}
            </Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 14 }}>
              <AccountValue label="Verification" value={profile.verification_tier} />
              <AccountValue label="Compliance" value={profile.compliance_status} />
              <AccountValue label="Availability" value={profile.is_available ? "Available" : "Not available"} />
              <AccountValue label="Operating status" value={profile.is_online ? "Online" : "Offline"} />
            </View>
            <View style={{ height: 1, backgroundColor: palette.border }} />
            <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "900" }}>
              Go-live checklist
            </Text>
            {(profile.go_live?.checks ?? []).map(check => (
              <View
                key={check.key}
                style={{ flexDirection: "row", alignItems: "flex-start", gap: 9 }}
              >
                <Text style={{ color: check.ok ? palette.greenDark : "#9A6B12", fontSize: 15, fontWeight: "900" }}>
                  {check.ok ? "✓" : "•"}
                </Text>
                <View style={{ flex: 1, gap: 3 }}>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
                    <Text style={{ color: palette.ink, fontSize: 12, fontWeight: "800" }}>
                      {check.label}
                    </Text>
                    <Text style={{ color: palette.muted, fontSize: 10 }}>
                      {check.required ? "Required" : "Optional"}
                    </Text>
                  </View>
                  {!check.ok && check.hint ? (
                    <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 16 }}>
                      {check.hint}
                    </Text>
                  ) : null}
                </View>
                <StatusPill tone={check.ok ? "green" : "gold"}>
                  {check.ok ? "Met" : "Pending"}
                </StatusPill>
              </View>
            ))}
            {(profile.go_live?.checks ?? []).length === 0 ? (
              <EmptyState
                title="Checklist unavailable"
                description="AFCON360 did not return the current go-live requirements. Refresh to try again."
              />
            ) : null}
            <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 16 }}>
              These checks are read directly from AFCON360 Transport. The app cannot approve a driver or bypass a requirement.
            </Text>
          </>
        ) : null}

        <ActionButton
          label={loading ? "Refreshing…" : "Refresh driver status"}
          disabled={loading}
          onPress={() => { setLoading(true); void load(); }}
        />
      </Panel>

      <Panel>
        <SectionTitle>Account and help</SectionTitle>
        <ActionButton
          label="Contact AFCON360 support"
          onPress={() => { void WebBrowser.openBrowserAsync("https://www.pamoja.space/support"); }}
        />
        <ActionButton
          label="Share AFCON360 Driver page"
          onPress={() => share("https://www.pamoja.space/apps", "AFCON360 Driver — official app information and downloads.")}
        />
        <ActionButton
          label="Privacy notice (website)"
          onPress={() => { void WebBrowser.openBrowserAsync("https://www.pamoja.space/apps/privacy"); }}
        />
        <ActionButton label="Delete AFCON360 account" onPress={() => router.push("/delete-account")} />
        <ActionButton label="Sign out" onPress={signOut} />
      </Panel>
      <Text style={{ color: palette.muted, fontSize: 12 }}>
        Vehicle registration, ownership changes and document review remain governed by AFCON360 Transport.
      </Text>
    </AppScreen>
  );
}
