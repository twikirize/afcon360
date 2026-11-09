import React, { useCallback, useState } from "react";
import { ActivityIndicator, Alert, AppState, Pressable, Text, View } from "react-native";
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

type TripHistoryScope = "upcoming" | "recent";

type TripHistoryItem = {
  booking_reference: string;
  status: string;
  booking_mode?: string;
  pickup_time?: string | null;
  pickup_schedule?: {
    local_datetime?: string;
    utc_datetime?: string;
    timezone_name?: string;
    utc_offset?: string;
    display_timezone_derived?: boolean;
  } | null;
  pickup?: { address?: string };
  dropoff?: { address?: string };
  passenger_count?: number;
  fare_amount?: string | null;
  currency?: string | null;
  payment_method?: string | null;
  payment_status?: string | null;
  can_mark_no_show?: boolean;
  created_at?: string | null;
  completed_at?: string | null;
};

type TripHistoryResponse = {
  data: {
    scope: TripHistoryScope;
    items: TripHistoryItem[];
    count: number;
    limit: number;
  };
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

function historyTime(item: TripHistoryItem) {
  const local = item.pickup_schedule?.local_datetime;
  if (local) {
    const timezone = item.pickup_schedule?.timezone_name;
    return timezone ? local + " · " + timezone : local;
  }
  return item.pickup_time ?? "Time not provided";
}

function HistoryTripCard({ item }: { item: TripHistoryItem }) {
  return (
    <View
      style={{
        gap: 10,
        padding: 13,
        borderRadius: 15,
        borderWidth: 1,
        borderColor: palette.border,
        backgroundColor: "#F8FBF9"
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <Text style={{ color: palette.ink, fontSize: 12, fontWeight: "900", flexShrink: 1 }}>
          {item.booking_reference}
        </Text>
        <StatusPill>{item.status}</StatusPill>
      </View>
      <Text style={{ color: palette.ink, fontSize: 14, lineHeight: 20, fontWeight: "800" }}>
        {item.pickup?.address ?? "Pickup details unavailable"} →{" "}
        {item.dropoff?.address ?? "Destination details unavailable"}
      </Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 14 }}>
        <TripDetail label="Pickup time" value={historyTime(item)} />
        <TripDetail
          label="Fare"
          value={
            item.fare_amount !== undefined && item.fare_amount !== null
              ? item.fare_amount + " " + (item.currency ?? "")
              : "Not provided"
          }
        />
        <TripDetail
          label="Passengers"
          value={item.passenger_count === undefined ? "Not provided" : String(item.passenger_count)}
        />
      </View>
      <Text style={{ color: palette.muted, fontSize: 12 }}>
        {(item.booking_mode ?? "Trip") + " · " + (item.payment_method ?? "Payment not provided")} ·{" "}
        {item.payment_status ?? "Payment status not provided"}
      </Text>
      {item.completed_at ? (
        <Text style={{ color: palette.muted, fontSize: 11 }}>
          Completed: {item.completed_at}
        </Text>
      ) : null}
    </View>
  );
}

export default function Trips() {
  const [trip, setTrip] = useState<ActiveTrip | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyScope, setHistoryScope] = useState<TripHistoryScope>("upcoming");
  const [historyItems, setHistoryItems] = useState<TripHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

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

  const loadHistory = useCallback(async (scope: TripHistoryScope) => {
    setHistoryLoading(true);
    try {
      const response = await authClient.request<TripHistoryResponse>(
        "/api/mobile/v1/driver/trips?scope=" + scope + "&limit=20"
      );
      setHistoryItems(response.data.items ?? []);
      setHistoryError(null);
    } catch (e) {
      setHistoryError(
        e instanceof Error
          ? e.message
          : "Trip history is temporarily unavailable. Please try again."
      );
    } finally {
      setHistoryLoaded(true);
      setHistoryLoading(false);
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

  useFocusEffect(
    useCallback(() => {
      void loadHistory(historyScope);
    }, [historyScope, loadHistory])
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
        description="Follow each server-confirmed trip step, review upcoming work and revisit completed trips."
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

      <Panel>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <SectionTitle>Trip history</SectionTitle>
          <StatusPill>{historyItems.length} trips</StatusPill>
        </View>
        <View style={{ flexDirection: "row", gap: 8 }}>
          {(["upcoming", "recent"] as const).map(scope => {
            const selected = historyScope === scope;
            return (
              <Pressable
                key={scope}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                onPress={() => setHistoryScope(scope)}
                style={{
                  flex: 1,
                  alignItems: "center",
                  paddingVertical: 11,
                  borderRadius: 12,
                  backgroundColor: selected ? palette.green : "#F1F5F2"
                }}
              >
                <Text style={{ color: selected ? "#FFFFFF" : palette.ink, fontSize: 13, fontWeight: "800" }}>
                  {scope === "upcoming" ? "Upcoming" : "Recent"}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {historyLoading ? <ActivityIndicator color={palette.green} /> : null}
        {historyError ? (
          <View style={{ gap: 8 }}>
            <Text accessibilityRole="alert" style={{ color: "#9A3A2F", fontSize: 13, lineHeight: 19 }}>
              {historyError}
            </Text>
            <ActionButton
              label="Retry trip history"
              disabled={historyLoading}
              onPress={() => { void loadHistory(historyScope); }}
            />
          </View>
        ) : null}
        {historyLoaded && !historyLoading && !historyError && historyItems.length === 0 ? (
          <EmptyState
            title={historyScope === "upcoming" ? "No upcoming trips" : "No recent trips"}
            description={
              historyScope === "upcoming"
                ? "Assigned scheduled trips will appear here when AFCON360 confirms them."
                : "Completed and past assigned trips will appear here."
            }
          />
        ) : null}
        {!historyError ? historyItems.map(item => (
          <HistoryTripCard key={item.booking_reference} item={item} />
        )) : null}
        <ActionButton
          label={historyLoading ? "Refreshing history…" : "Refresh history"}
          disabled={historyLoading}
          onPress={() => { void loadHistory(historyScope); }}
        />
      </Panel>
    </AppScreen>
  );
}
