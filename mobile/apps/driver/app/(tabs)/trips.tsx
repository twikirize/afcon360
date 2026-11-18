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

function TripDetail({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1, minWidth: 120, gap: 3 }}>
      <Text style={{ color: palette.muted, fontSize: 11, fontWeight: "700" }}>{label}</Text>
      <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "800" }}>{value}</Text>
    </View>
  );
}

export default function Trips() {
  const [trip, setTrip] = useState<ActiveTrip | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await authClient.request<{ data: ActiveTrip | null }>(
        "/api/mobile/v1/driver/trips/active"
      );
      setTrip(response.data ?? null);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load your active trip.");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();

      // The Trips tab and Driver dashboard share the active-trip API.
      // Poll only while Trips is visible and refresh immediately on resume.
      const subscription = AppState.addEventListener("change", state => {
        if (state === "active") void load();
      });
      const interval = setInterval(() => {
        if (AppState.currentState === "active") void load();
      }, 15000);

      return () => {
        clearInterval(interval);
        subscription.remove();
      };
    }, [load])
  );

  async function advance(action: string) {
    if (!trip) return;
    setBusy(true);
    try {
      await authClient.request(
        "/api/mobile/v1/driver/trips/" + encodeURIComponent(trip.booking_reference) + "/status",
        { method: "POST", body: { action } }
      );
      await load();
    } catch (e) {
      Alert.alert(
        "Trip update rejected",
        e instanceof Error ? e.message : "AFCON360 could not update this trip."
      );
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function confirmCash() {
    if (!trip) return;
    Alert.alert(
      "Confirm cash receipt",
      "Confirm only after the passenger has actually paid you in cash.",
      [
        { text: "Not yet", style: "cancel" },
        {
          text: "Confirm cash received",
          onPress: async () => {
            setBusy(true);
            try {
              await authClient.request(
                "/api/mobile/v1/driver/trips/" +
                  encodeURIComponent(trip.booking_reference) +
                  "/payment/confirm-cash",
                { method: "POST", body: {} }
              );
              await load();
            } catch (e) {
              Alert.alert(
                "Cash receipt not recorded",
                e instanceof Error ? e.message : "AFCON360 could not confirm cash receipt."
              );
            } finally {
              setBusy(false);
            }
          }
        }
      ]
    );
  }

  const action = trip ? nextAction[trip.status.toLowerCase()] : undefined;
  const canConfirmCash =
    trip?.status.toLowerCase() === "completed" &&
    trip.payment_method === "cash" &&
    trip.payment_status !== "captured";

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Trips"
        title="Your assigned work."
        description="Follow each server-confirmed trip step. Trip completion and payment settlement are separate."
      />
      <Panel>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <SectionTitle>Current trip</SectionTitle>
          {trip ? <StatusPill>{trip.status}</StatusPill> : null}
        </View>

        {loading && !trip ? <ActivityIndicator color={palette.green} /> : null}
        {error ? (
          <Text accessibilityRole="alert" style={{ color: "#9A3A2F", fontSize: 13, lineHeight: 19 }}>
            {error}
          </Text>
        ) : null}
        {!loading && !error && !trip ? (
          <EmptyState
            title="No active trip"
            description="When you accept an offer, its confirmed pickup, destination and next action appear here."
          />
        ) : null}

        {trip ? (
          <>
            <Text style={{ color: palette.ink, fontSize: 18, fontWeight: "900" }}>
              {trip.booking_reference}
            </Text>
            <View style={{ gap: 5, padding: 13, borderRadius: 14, backgroundColor: "#F8FBF9" }}>
              <TripDetail label="Pickup" value={trip.pickup?.address ?? "Not provided"} />
              <View style={{ height: 1, backgroundColor: palette.border }} />
              <TripDetail label="Destination" value={trip.dropoff?.address ?? "Not provided"} />
            </View>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 14 }}>
              <TripDetail
                label="Fare"
                value={
                  trip.fare_amount !== undefined
                    ? trip.fare_amount + " " + (trip.currency ?? "")
                    : "Not provided"
                }
              />
              <TripDetail label="Payment method" value={trip.payment_method ?? "Not provided"} />
              <TripDetail label="Payment status" value={trip.payment_status ?? "Pending"} />
            </View>
            {action ? (
              <ActionButton
                label={busy ? "Updating trip…" : action.label}
                disabled={busy}
                onPress={() => advance(action.action)}
              />
            ) : (
              <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>
                There is no further trip action available for this server-reported status.
              </Text>
            )}
            {canConfirmCash ? (
              <View style={{ gap: 8 }}>
                <View style={{ padding: 12, borderRadius: 13, backgroundColor: palette.warningSoft }}>
                  <Text style={{ color: palette.ink, fontSize: 12, lineHeight: 18 }}>
                    Only confirm cash after you have physically received the passenger’s payment.
                  </Text>
                </View>
                <ActionButton
                  label={busy ? "Recording receipt…" : "Confirm cash received"}
                  disabled={busy}
                  onPress={confirmCash}
                />
              </View>
            ) : null}
          </>
        ) : null}

        <ActionButton
          label={loading ? "Refreshing…" : "Refresh trip"}
          disabled={loading || busy}
          onPress={() => { setLoading(true); void load(); }}
        />
      </Panel>
    </AppScreen>
  );
}
