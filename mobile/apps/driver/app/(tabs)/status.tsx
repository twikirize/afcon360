import React, { useCallback, useState } from "react";
import { ActivityIndicator, Alert, AppState, Text, View } from "react-native";
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
import { useFocusEffect } from "expo-router";
import { MobileAuthError } from "@afcon360/mobile-core";
import { authClient } from "../../src/services/api";

type DriverStatusData = {
  driver_code: string;
  is_online: boolean;
  is_available: boolean;
  verification_tier: string;
  compliance_status: string;
  go_live?: { ready: boolean; checks?: Array<{ key: string; label: string; ok: boolean; required: boolean; hint?: string }> };
  operational_preferences?: {
    service_types?: string[];
    vehicle_classes?: string[];
    operational_zones?: string[];
    max_passenger_capacity?: number;
    max_luggage_capacity?: number;
    auto_accept_bookings?: boolean;
    max_concurrent_bookings?: number;
  };
  compliance?: {
    license_verified?: boolean;
    license_expiry?: string | null;
    background_check_status?: string;
    police_clearance_verified?: boolean;
    next_training_due?: string | null;
    requires_retraining?: boolean;
  };
};

function StatusValue({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1, minWidth: 135, gap: 3 }}>
      <Text style={{ color: palette.muted, fontSize: 11, fontWeight: "700" }}>{label}</Text>
      <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "800" }}>{value}</Text>
    </View>
  );
}

function listValue(value?: string[]) {
  return value && value.length ? value.join(", ") : "Not set";
}

export default function DriverStatus() {
  const [data, setData] = useState<DriverStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await authClient.request<{ data: DriverStatusData }>("/api/mobile/v1/driver/me");
      setData(response.data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Driver status could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
      const subscription = AppState.addEventListener("change", state => {
        if (state === "active") void load();
      });
      return () => subscription.remove();
    }, [load])
  );

  async function toggleOnline() {
    if (!data) return;
    if (!data.is_online && !data.go_live?.ready) {
      Alert.alert(
        "Complete your go-live checks",
        "AFCON360 Transport must confirm your identity, compliance, licence and any required vehicle before you can go online."
      );
      return;
    }
    setBusy(true);
    try {
      await authClient.request("/api/mobile/v1/driver/status", {
        method: "POST",
        body: data.is_online
          ? { is_online: false, is_available: false }
          : { is_online: true, is_available: true }
      });
      await load();
    } catch (e) {
      Alert.alert(
        "Status not changed",
        e instanceof MobileAuthError ? e.message : "AFCON360 could not change your online status."
      );
    } finally {
      setBusy(false);
    }
  }

  const preferences = data?.operational_preferences;
  const compliance = data?.compliance;

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Driver status"
        title="Your operating status."
        description="Review your current availability and the operating preferences held by AFCON360 Transport."
      />

      <Panel>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <SectionTitle>Availability</SectionTitle>
          <StatusPill tone={data?.is_online ? "green" : "gold"}>
            {data?.is_online ? "Online" : "Offline"}
          </StatusPill>
        </View>
        {loading && !data ? <ActivityIndicator color={palette.green} /> : null}
        {error ? (
          <View style={{ gap: 8 }}>
            <Text accessibilityRole="alert" style={{ color: "#9A3A2F", fontSize: 13, lineHeight: 19 }}>{error}</Text>
            <ActionButton label="Retry status" disabled={loading} onPress={() => { setLoading(true); void load(); }} />
          </View>
        ) : null}
        {data ? (
          <>
            <Text style={{ color: palette.ink, fontSize: 18, fontWeight: "900" }}>Driver {data.driver_code}</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 14 }}>
              <StatusValue label="Availability" value={data.is_available ? "Available" : "Not available"} />
              <StatusValue label="Verification" value={data.verification_tier} />
              <StatusValue label="Compliance" value={data.compliance_status} />
            </View>
            <ActionButton
              label={busy ? "Updating…" : data.is_online ? "Go offline" : "Go online"}
              disabled={busy || (!data.is_online && !data.go_live?.ready)}
              onPress={toggleOnline}
            />
            {!data.go_live?.ready && !data.is_online ? (
              <View style={{ gap: 5, padding: 12, borderRadius: 13, backgroundColor: palette.warningSoft }}>
                <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "900" }}>Not cleared for dispatch</Text>
                <Text style={{ color: palette.ink, fontSize: 12, lineHeight: 18 }}>
                  Complete the outstanding items in Account before accepting live work.
                </Text>
              </View>
            ) : null}
          </>
        ) : null}
      </Panel>

      <Panel>
        <SectionTitle>Operating preferences</SectionTitle>
        {preferences ? (
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 16 }}>
            <StatusValue label="Driving services" value={listValue(preferences.service_types)} />
            <StatusValue label="Vehicle classes" value={listValue(preferences.vehicle_classes)} />
            <StatusValue label="Operating zones" value={listValue(preferences.operational_zones)} />
            <StatusValue label="Passenger capacity" value={String(preferences.max_passenger_capacity ?? "Not set")} />
            <StatusValue label="Luggage capacity" value={String(preferences.max_luggage_capacity ?? "Not set")} />
            <StatusValue label="Concurrent trips" value={String(preferences.max_concurrent_bookings ?? "Not set")} />
            <StatusValue label="Auto-accept" value={preferences.auto_accept_bookings ? "Enabled" : "Disabled"} />
          </View>
        ) : (
          <EmptyState title="Preferences unavailable" description="AFCON360 has not returned your operating preferences." />
        )}
        <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 16 }}>
          These settings are displayed from your Transport profile. Changes to operating permissions and preferences remain controlled by AFCON360.
        </Text>
      </Panel>

      <Panel>
        <SectionTitle>Compliance status</SectionTitle>
        {compliance ? (
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 16 }}>
            <StatusValue label="Licence verification" value={compliance.license_verified ? "Verified" : "Not verified"} />
            <StatusValue label="Licence expiry" value={compliance.license_expiry ?? "Not provided"} />
            <StatusValue label="Background check" value={compliance.background_check_status ?? "Pending"} />
            <StatusValue label="Police clearance" value={compliance.police_clearance_verified ? "Verified" : "Not verified"} />
            <StatusValue label="Next training" value={compliance.next_training_due ?? "Not scheduled"} />
            <StatusValue label="Retraining required" value={compliance.requires_retraining ? "Yes" : "No"} />
          </View>
        ) : (
          <EmptyState title="Compliance details unavailable" description="Refresh to load the latest checks." />
        )}
      </Panel>

      <ActionButton label={loading ? "Refreshing…" : "Refresh status"} disabled={loading} onPress={() => { setLoading(true); void load(); }} />
    </AppScreen>
  );
}
