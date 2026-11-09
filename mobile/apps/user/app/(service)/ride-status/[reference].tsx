import React, { useCallback, useState } from "react";
import { ActivityIndicator, AppState, Pressable, Text, View } from "react-native";
import { useFocusEffect, useLocalSearchParams } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, StatusPill, palette } from "@afcon360/mobile-ui";
import { authClient } from "../../../src/services/api";

type RequestData = {
  request_id: string;
  status: string;
  cycle?: { status: string; deadline?: string | null; terminal_reason?: string | null };
  converted?: boolean;
  booking_status?: string;
  fare_estimate?: { amount?: number | null; currency?: string | null };
  payment_method?: string;
  created_at?: string | null;
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
    if (!reference) {
      setError("This ride request reference is missing. Return to your activity and open the request again.");
      setLoading(false);
      return;
    }
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

  useFocusEffect(
    useCallback(() => {
      void refresh();

      // Poll only while this request screen is visible and the app is active.
      // Resume with a fresh server state after backgrounding the app.
      const subscription = AppState.addEventListener("change", state => {
        if (state === "active") void refresh();
      });
      const timer = setInterval(() => {
        if (AppState.currentState === "active") void refresh();
      }, 12000);

      return () => {
        clearInterval(timer);
        subscription.remove();
      };
    }, [refresh])
  );

  const requestState = data?.cycle?.status ?? data?.status ?? "Waiting for status";
  const quotedFare = data?.fare_estimate;
  const payment = data?.payment;

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Ride tracking"
        title="Your driver journey."
        description="This reference tracks your request through matching and assignment. A ride is not driver-confirmed until Transport commits a driver and vehicle."
      />
      <Panel>
        <StatusPill tone={data?.converted ? "green" : "gold"}>
          {data?.converted ? "Driver assigned" : requestState}
        </StatusPill>
        <SectionTitle>Request reference</SectionTitle>
        <Text selectable style={{ color: palette.ink, fontSize: 15, fontWeight: "900" }}>
          {reference || "Reference unavailable"}
        </Text>
        {loading ? <ActivityIndicator color={palette.green} /> : null}
        {error ? (
          <Text accessibilityRole="alert" style={{ color: "#9A3A2F", fontSize: 13, lineHeight: 19 }}>
            {error}
          </Text>
        ) : null}
        <Pressable
          onPress={() => { setLoading(true); void refresh(); }}
          accessibilityRole="button"
          accessibilityLabel="Refresh ride request status"
          style={{ paddingVertical: 10 }}
        >
          <Text style={{ color: palette.greenDark, fontWeight: "800" }}>Refresh status</Text>
        </Pressable>
      </Panel>

      {data ? (
        <Panel>
          <SectionTitle>Request details</SectionTitle>
          {quotedFare?.amount != null ? (
            <Text style={{ color: palette.ink, fontWeight: "800" }}>
              Quoted fare: {quotedFare.amount} {quotedFare.currency ?? ""}
            </Text>
          ) : null}
          <Text style={{ color: palette.muted, fontSize: 12 }}>
            Payment choice: {data.payment_method ?? payment?.method ?? "Not available"}
          </Text>
          {payment ? (
            <Text style={{ color: palette.muted, fontSize: 12 }}>
              Payment status: {payment.status ?? "Not available"}
              {payment.amount != null ? ` · ${payment.amount} ${payment.currency ?? ""}` : ""}
            </Text>
          ) : null}
          {!data.converted ? (
            <Text style={{ color: palette.muted, fontSize: 13, lineHeight: 19 }}>
              This request has not yet been converted into an assigned booking. The status above is the latest state reported by AFCON360 Transport.
              {data.cycle?.terminal_reason ? ` ${data.cycle.terminal_reason}` : ""}
            </Text>
          ) : null}
        </Panel>
      ) : null}

      {data?.converted ? (
        <Panel>
          <SectionTitle>Your assigned driver</SectionTitle>
          <Text style={{ color: palette.ink, fontWeight: "800" }}>
            {data.driver?.display_name ?? "Driver assigned"}
          </Text>
          {data.driver?.rating != null ? (
            <Text style={{ color: palette.muted }}>Rating {data.driver.rating.toFixed(1)}</Text>
          ) : null}
          <SectionTitle>Vehicle</SectionTitle>
          <Text style={{ color: palette.ink }}>
            {[data.vehicle?.make, data.vehicle?.model].filter(Boolean).join(" ") || "Vehicle assigned"}
          </Text>
          {data.vehicle?.license_plate ? (
            <Text style={{ color: palette.ink, fontWeight: "800" }}>{data.vehicle.license_plate}</Text>
          ) : null}
          {data.booking_status ? (
            <Text style={{ color: palette.muted }}>Trip status: {data.booking_status}</Text>
          ) : null}
        </Panel>
      ) : null}
    </AppScreen>
  );
}
