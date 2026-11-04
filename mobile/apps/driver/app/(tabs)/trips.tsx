import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Text, View } from "react-native";
import { AppScreen, PageHeader, Panel, EmptyState, StatusPill, ActionButton, palette } from "@afcon360/mobile-ui";
import { authClient } from "../../src/services/api";

type ActiveTrip = {
  booking_reference: string;
  status: string;
  pickup?: { address?: string };
  dropoff?: { address?: string };
  payment_method?: string;
  payment_status?: string;
  fare_amount?: string;
  currency?: string;
};
const nextAction: Record<string, { action: string; label: string }> = {
  assigned: { action: "en_route", label: "Start driving to pickup" },
  driver_en_route: { action: "arrive", label: "I have arrived" },
  pickup_arrived: { action: "start", label: "Start trip" },
  in_progress: { action: "complete", label: "Complete trip" }
};

export default function Trips() {
  const [trip, setTrip] = useState<ActiveTrip | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const response = await authClient.request<{ data: ActiveTrip | null }>("/api/mobile/v1/driver/trips/active");
      setTrip(response.data ?? null);
    } catch (e) {
      Alert.alert("Trip status unavailable", e instanceof Error ? e.message : "Could not load your active trip.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function advance(action: string) {
    if (!trip) return;
    setBusy(true);
    try {
      await authClient.request("/api/mobile/v1/driver/trips/" + encodeURIComponent(trip.booking_reference) + "/status", { method: "POST", body: { action } });
      await load();
    } catch (e) {
      Alert.alert("Trip update rejected", e instanceof Error ? e.message : "AFCON360 could not update this trip.");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function confirmCash() {
    if (!trip) return;
    Alert.alert("Confirm cash receipt", "Confirm only after the passenger has actually paid you in cash.", [
      { text: "Not yet", style: "cancel" },
      { text: "Confirm cash received", onPress: async () => {
        setBusy(true);
        try {
          await authClient.request("/api/mobile/v1/driver/trips/" + encodeURIComponent(trip.booking_reference) + "/payment/confirm-cash", { method: "POST", body: {} });
          await load();
        } catch (e) {
          Alert.alert("Cash receipt not recorded", e instanceof Error ? e.message : "AFCON360 could not confirm cash receipt.");
        } finally { setBusy(false); }
      }}
    ]);
  }

  const action = trip ? nextAction[trip.status.toLowerCase()] : undefined;
  return <AppScreen>
    <PageHeader eyebrow="Trips" title="Your assigned work." description="Advance each trip through the Transport state machine. Payment and completion remain separate states." />
    <Panel>
      {loading ? <ActivityIndicator color={palette.green} /> : null}
      {!loading && !trip ? <EmptyState title="No active trip" description="When you accept an offer, its pickup, destination and next action appear here." /> : null}
      {trip ? (
        <>
          <StatusPill>{trip.status}</StatusPill>
          <Text style={{ color: palette.ink, fontWeight: "900" }}>{trip.booking_reference}</Text>
          <Text style={{ color: palette.ink }}>{trip.pickup?.address ?? "Pickup"} → {trip.dropoff?.address ?? "Destination"}</Text>
          <Text style={{ color: palette.muted }}>{trip.fare_amount ?? "—"} {trip.currency ?? ""} · {trip.payment_method ?? "Payment"} · {trip.payment_status ?? "Pending"}</Text>
          {action ? <ActionButton label={busy ? "Updating trip…" : action.label} disabled={busy} onPress={() => advance(action.action)} /> : null}
          {trip.status.toLowerCase() === "completed" && trip.payment_method === "cash" && trip.payment_status !== "captured" ? (
            <ActionButton label="Confirm cash received" disabled={busy} onPress={confirmCash} />
          ) : null}
        </>
      ) : null}
    </Panel>
    <ActionButton label="Refresh trip" disabled={loading || busy} onPress={() => { setLoading(true); void load(); }} />
  </AppScreen>;
}
