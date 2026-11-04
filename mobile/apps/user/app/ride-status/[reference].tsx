import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, StatusPill, palette } from "@afcon360/mobile-ui";
import { authClient } from "../../src/services/api";

type RequestData = {
  request_id: string;
  status: string;
  cycle?: { status: string; deadline?: string | null; terminal_reason?: string | null };
  converted?: boolean;
  booking_status?: string;
  driver?: { display_name?: string; rating?: number | null } | null;
  vehicle?: { make?: string; model?: string; license_plate?: string; vehicle_class?: string } | null;
  payment?: { method?: string; status?: string; amount?: number; currency?: string };
};

export default function RideStatusScreen() {
  const params = useLocalSearchParams<{ reference: string }>();
  const reference = String(params.reference ?? "");
  const [data, setData] = useState<RequestData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!reference) return;
    try {
      const response = await authClient.request<{ success: boolean; data: RequestData }>(
        "/api/mobile/v1/transport/ride-requests/" + encodeURIComponent(reference)
      );
      setData(response.data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not refresh this ride.");
    } finally {
      setLoading(false);
    }
  }, [reference]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => { void refresh(); }, 12000);
    return () => clearInterval(timer);
  }, [refresh]);

  return (
    <AppScreen>
      <PageHeader eyebrow="Ride tracking" title="Your driver journey." description="This reference tracks your request through matching and assignment. A ride is not driver-confirmed until Transport commits a driver and vehicle." />
      <Panel>
        <StatusPill tone={data?.converted ? "green" : "gold"}>{data?.converted ? "Driver assigned" : data?.cycle?.status ?? data?.status ?? "Loading status"}</StatusPill>
        <SectionTitle>Request reference</SectionTitle>
        <Text selectable style={{ color: palette.ink, fontSize: 15, fontWeight: "900" }}>{reference}</Text>
        {loading ? <ActivityIndicator color={palette.green} /> : null}
        {error ? <Text style={{ color: "#9A3A2F", fontSize: 13 }}>{error}</Text> : null}
        <Pressable onPress={() => { setLoading(true); void refresh(); }} accessibilityRole="button" style={{ paddingVertical: 10 }}>
          <Text style={{ color: palette.greenDark, fontWeight: "800" }}>Refresh status</Text>
        </Pressable>
      </Panel>
      {data?.converted ? (
        <Panel>
          <SectionTitle>Your assigned driver</SectionTitle>
          <Text style={{ color: palette.ink, fontWeight: "800" }}>{data.driver?.display_name ?? "Driver assigned"}</Text>
          {data.driver?.rating != null ? <Text style={{ color: palette.muted }}>Rating {data.driver.rating.toFixed(1)}</Text> : null}
          <SectionTitle>Vehicle</SectionTitle>
          <Text style={{ color: palette.ink }}>{[data.vehicle?.make, data.vehicle?.model].filter(Boolean).join(" ") || "Vehicle assigned"}</Text>
          {data.vehicle?.license_plate ? <Text style={{ color: palette.ink, fontWeight: "800" }}>{data.vehicle.license_plate}</Text> : null}
          {data.booking_status ? <Text style={{ color: palette.muted }}>Trip status: {data.booking_status}</Text> : null}
        </Panel>
      ) : (
        <Panel>
          <SectionTitle>Matching in progress</SectionTitle>
          <Text style={{ color: palette.muted, fontSize: 13, lineHeight: 19 }}>AFCON360 is checking driver responses. We’ll show driver and vehicle details here only after a valid assignment is committed.</Text>
        </Panel>
      )}
    </AppScreen>
  );
}
