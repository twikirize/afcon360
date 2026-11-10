import React, { useCallback, useRef, useState } from "react";
import { ActivityIndicator, Alert, AppState, Pressable, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import {
  ActionButton,
  AppScreen,
  EmptyState,
  PageHeader,
  Panel,
  SectionTitle,
  ServiceTile,
  StatusPill,
  palette
} from "@afcon360/mobile-ui";
import { MobileAuthError } from "@afcon360/mobile-core";
import { authClient } from "../../src/services/api";
import { DriverMapPanel } from "../../src/map/DriverMapPanel";
import { requestForegroundDriverLocation } from "../../src/location/permissions";

type DriverProfile = {
  driver_code: string;
  verification_tier: string;
  compliance_status: string;
  is_online: boolean;
  is_available: boolean;
  go_live?: {
    ready: boolean;
    checks?: Array<{
      key: string;
      label: string;
      ok: boolean;
      required: boolean;
      hint?: string;
    }>;
  };
  performance?: {
    reliability_score?: number | null;
    safety_score?: number | null;
    acceptance_rate?: string | null;
    cancellation_rate?: string | null;
    total_trips?: number | null;
    completed_trips?: number | null;
    total_distance_km?: string | null;
    average_rating?: string | null;
    total_ratings?: number | null;
  };
  assigned_vehicle?: {
    make?: string | null;
    model?: string | null;
    year?: number | null;
    license_plate?: string | null;
    vehicle_class?: string | null;
    passenger_capacity?: number | null;
  } | null;
};

type Offer = {
  booking_reference: string;
  status: string;
  ttl_remaining?: number;
  pickup?: { text?: string };
  destination?: { text?: string };
  fare_estimate?: { amount?: number; currency?: string };
  ride_class?: string;
  passenger_count?: number;
  vehicle?: { make?: string; model?: string; license_plate?: string };
};

type ActiveTrip = {
  booking_reference: string;
  status: string;
  pickup?: { address?: string };
  dropoff?: { address?: string };
  payment_method?: string;
  payment_status?: string;
  fare_amount?: string;
  currency?: string;
  can_cancel?: boolean;
  can_mark_no_show?: boolean;
  pickup_schedule?: {
    local_datetime?: string;
    timezone_name?: string;
  } | null;
};

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ gap: 2 }}>
      <Text style={{ color: palette.muted, fontSize: 11, fontWeight: "700" }}>{label}</Text>
      <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "700" }}>{value}</Text>
    </View>
  );
}

export default function DriverHome() {
  const router = useRouter();
  const [profile, setProfile] = useState<DriverProfile | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [activeTrip, setActiveTrip] = useState<ActiveTrip | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onlineRef = useRef(false);
  const coreLoadInFlight = useRef(false);

  const load = useCallback(async () => {
    if (coreLoadInFlight.current) return;
    coreLoadInFlight.current = true;
    try {
      const [me, tripResponse] = await Promise.all([
        authClient.request<{ data: DriverProfile }>("/api/mobile/v1/driver/me"),
        authClient.request<{ data: ActiveTrip | null }>("/api/mobile/v1/driver/trips/active")
      ]);
      onlineRef.current = me.data.is_online === true;
      setProfile(me.data);
      setActiveTrip(tripResponse.data ?? null);
      if (!onlineRef.current) setOffers([]);
      setError(null);
    } catch (e) {
      onlineRef.current = false;
      setError(e instanceof Error ? e.message : "Driver information could not be loaded.");
    } finally {
      coreLoadInFlight.current = false;
      setLoading(false);
    }
  }, []);

  const loadOffers = useCallback(async () => {
    if (
      !onlineRef.current ||
      AppState.currentState !== "active"
    ) return { ok: false, count: 0 };

    try {
      const response = await authClient.request<{ data: { offers: Offer[] } }>(
        "/api/mobile/v1/driver/offers"
      );
      const next = response.data.offers ?? [];
      setOffers(next);
      return { ok: true, count: next.length };
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ride offers could not be refreshed.");
      return { ok: false, count: 0 };
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      let offerTimer: ReturnType<typeof setTimeout> | null = null;
      let coreTimer: ReturnType<typeof setInterval> | null = null;
      let offerDelay = 4000;
      let offerPollInFlight = false;

      const clearOfferTimer = () => {
        if (offerTimer) {
          clearTimeout(offerTimer);
          offerTimer = null;
        }
      };

      const scheduleOffers = () => {
        clearOfferTimer();
        if (!active || AppState.currentState !== "active") return;
        offerTimer = setTimeout(() => { void pollOffers(); }, offerDelay);
      };

      const pollOffers = async () => {
        if (!active || AppState.currentState !== "active") return;
        if (!onlineRef.current) {
          offerDelay = Math.min(offerDelay * 2, 30000);
          scheduleOffers();
          return;
        }
        if (offerPollInFlight) {
          scheduleOffers();
          return;
        }

        offerPollInFlight = true;
        try {
          const result = await loadOffers();
          if (!active) return;
          offerDelay = result.ok && result.count > 0
            ? 4000
            : Math.min(offerDelay * 2, 30000);
        } finally {
          offerPollInFlight = false;
          scheduleOffers();
        }
      };

      const refreshWorkspace = async () => {
        clearOfferTimer();
        await load();
        if (!active) return;
        offerDelay = 4000;
        void pollOffers();
      };

      void refreshWorkspace();
      coreTimer = setInterval(() => {
        if (AppState.currentState === "active") void refreshWorkspace();
      }, 15000);

      const subscription = AppState.addEventListener("change", state => {
        if (state === "active") {
          void refreshWorkspace();
        } else {
          clearOfferTimer();
        }
      });

      return () => {
        active = false;
        clearOfferTimer();
        if (coreTimer) clearInterval(coreTimer);
        subscription.remove();
      };
    }, [load, loadOffers])
  );

  async function toggleOnline() {
    if (!profile) return;
    setBusy(true);
    try {
      await authClient.request("/api/mobile/v1/driver/status", {
        method: "POST",
        body: profile.is_online
          ? { is_online: false, is_available: false }
          : { is_online: true, is_available: true }
      });
      await load();
    } catch (e) {
      Alert.alert(
        "Availability not changed",
        e instanceof MobileAuthError
          ? e.message
          : "AFCON360 could not update driver availability. Review your go-live checklist."
      );
    } finally {
      setBusy(false);
    }
  }

  async function sendLocation() {
    setBusy(true);
    try {
      const result = await requestForegroundDriverLocation();
      if (!result.granted) {
        Alert.alert(
          "Location permission needed",
          "Allow location while using AFCON360 Driver to share your current position."
        );
        return;
      }
      await authClient.request("/api/mobile/v1/driver/location", {
        method: "POST",
        body: {
          ...result.location,
          client_ts: result.location.observedAt
        }
      });
      Alert.alert("Location updated", "Your current location was sent to AFCON360 Transport.");
    } catch (e) {
      Alert.alert(
        "Location not updated",
        e instanceof Error ? e.message : "AFCON360 could not publish your location."
      );
    } finally {
      setBusy(false);
    }
  }

  async function respondToOffer(offer: Offer, action: "accept" | "decline") {
    setBusy(true);
    try {
      const path = action === "accept" ? "accept" : "decline";
      await authClient.request(
        "/api/mobile/v1/driver/offers/" +
          encodeURIComponent(offer.booking_reference) +
          "/" +
          path,
        { method: "POST", body: {} }
      );
      await load();
      await loadOffers();
      Alert.alert(
        action === "accept" ? "Ride accepted" : "Offer declined",
        action === "accept"
          ? "AFCON360 has confirmed the driver assignment."
          : "This offer has been declined."
      );
      await load();
    } catch (e) {
      Alert.alert(
        "Offer response not accepted",
        e instanceof MobileAuthError
          ? e.message
          : "This offer may have expired or been assigned elsewhere."
      );
      await load();
    } finally {
      setBusy(false);
    }
  }

  const goLiveReady = profile?.go_live?.ready ?? false;

  return (
    <AppScreen>
      <PageHeader
        eyebrow="AFCON360 Driver"
        title="Your driving workspace."
        description="Manage your availability, review ride offers and keep your assigned trip up to date."
      />

      <Panel>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <SectionTitle>Driver status</SectionTitle>
          <StatusPill tone={profile?.is_online ? "green" : "gold"}>
            {profile?.is_online ? "Online" : "Offline"}
          </StatusPill>
        </View>

        {loading && !profile ? <ActivityIndicator color={palette.green} /> : null}
        {error ? (
          <View style={{ gap: 8 }}>
            <Text accessibilityRole="alert" style={{ color: "#9A3A2F", fontSize: 13, lineHeight: 19 }}>
              {error}
            </Text>
            <ActionButton
              label={loading ? "Refreshing…" : "Retry loading driver status"}
              disabled={loading || busy}
              onPress={() => { setLoading(true); void load(); }}
            />
          </View>
        ) : null}

        {profile ? (
          <>
            <Text style={{ color: palette.ink, fontSize: 19, fontWeight: "900" }}>
              Driver {profile.driver_code}
            </Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              <StatusPill tone="neutral">{profile.verification_tier} verification</StatusPill>
              <StatusPill tone="neutral">{profile.compliance_status} compliance</StatusPill>
              <StatusPill tone={profile.is_available ? "green" : "gold"}>
                {profile.is_available ? "Available" : "Not available"}
              </StatusPill>
            </View>

            {!goLiveReady && !profile.is_online ? (
              <View style={{ gap: 8, padding: 13, borderRadius: 14, backgroundColor: palette.warningSoft }}>
                <Text style={{ color: palette.ink, fontWeight: "900", fontSize: 14 }}>
                  Complete your go-live checks
                </Text>
                {(profile.go_live?.checks ?? [])
                  .filter(item => item.required)
                  .map(item => (
                    <View key={item.key} style={{ flexDirection: "row", alignItems: "flex-start", gap: 8 }}>
                      <Text style={{ color: item.ok ? palette.greenDark : "#9A6B12", fontWeight: "900" }}>
                        {item.ok ? "✓" : "•"}
                      </Text>
                      <View style={{ flex: 1, gap: 2 }}>
                        <Text style={{ color: palette.ink, fontSize: 12, fontWeight: "700" }}>
                          {item.label}
                        </Text>
                        {!item.ok && item.hint ? (
                          <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 16 }}>
                            {item.hint}
                          </Text>
                        ) : null}
                      </View>
                    </View>
                  ))}
              </View>
            ) : null}

            <ActionButton
              label={
                busy
                  ? "Updating availability…"
                  : profile.is_online
                    ? "Go offline"
                    : goLiveReady
                      ? "Go online"
                      : "Complete checks to go online"
              }
              disabled={busy || (!profile.is_online && !goLiveReady)}
              onPress={toggleOnline}
            />
            <ActionButton
              label={busy ? "Please wait…" : "Share current location"}
              disabled={busy || !profile.is_online}
              onPress={sendLocation}
            />
            <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 16 }}>
              Location is requested only when you tap the button. Background tracking is not enabled.
            </Text>
          </>
        ) : null}

        {!loading && !profile && !error ? (
          <EmptyState
            title="Driver profile unavailable"
            description="Your approved driver profile could not be found. Refresh or contact AFCON360 support."
          />
        ) : null}

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Refresh driver status and ride offers"
          disabled={loading || busy}
          onPress={() => { setLoading(true); void load(); }}
          style={{ alignSelf: "flex-start", paddingVertical: 7, opacity: loading || busy ? 0.5 : 1 }}
        >
          <Text style={{ color: palette.greenDark, fontWeight: "800" }}>Refresh dashboard</Text>
        </Pressable>
      </Panel>

      <DriverMapPanel />

      <Panel>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <SectionTitle>Driving performance</SectionTitle>
          <StatusPill tone="neutral">
            {profile?.performance?.total_trips === undefined || profile.performance.total_trips === null
              ? "No summary"
              : String(profile.performance.total_trips) + " trips"}
          </StatusPill>
        </View>
        {profile?.performance ? (
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 14 }}>
            <DetailRow label="Average rating" value={profile.performance.average_rating ?? "Not rated"} />
            <DetailRow
              label="Total ratings"
              value={profile.performance.total_ratings === undefined || profile.performance.total_ratings === null
                ? "Not available"
                : String(profile.performance.total_ratings)}
            />
            <DetailRow
              label="Reliability score"
              value={profile.performance.reliability_score === undefined || profile.performance.reliability_score === null
                ? "Not available"
                : String(profile.performance.reliability_score) + "/100"}
            />
            <DetailRow
              label="Safety score"
              value={profile.performance.safety_score === undefined || profile.performance.safety_score === null
                ? "Not available"
                : String(profile.performance.safety_score) + "/100"}
            />
            <DetailRow label="Acceptance rate" value={profile.performance.acceptance_rate ? profile.performance.acceptance_rate + "%" : "Not available"} />
            <DetailRow label="Cancellation rate" value={profile.performance.cancellation_rate ? profile.performance.cancellation_rate + "%" : "Not available"} />
            <DetailRow
              label="Completed trips"
              value={profile.performance.completed_trips === undefined || profile.performance.completed_trips === null
                ? "Not available"
                : String(profile.performance.completed_trips)}
            />
            <DetailRow
              label="Total distance"
              value={profile.performance.total_distance_km ? profile.performance.total_distance_km + " km" : "Not available"}
            />
            <DetailRow
              label="Total driving time"
              value={profile.performance.total_duration_minutes === undefined || profile.performance.total_duration_minutes === null
                ? "Not available"
                : String(profile.performance.total_duration_minutes) + " min"}
            />
          </View>
        ) : (
          <Text style={{ color: palette.muted, fontSize: 12 }}>
            Performance information is not available from Transport yet.
          </Text>
        )}
        {profile?.assigned_vehicle ? (
          <View style={{ padding: 12, borderRadius: 13, backgroundColor: "#F8FBF9", gap: 4 }}>
            <Text style={{ color: palette.muted, fontSize: 11, fontWeight: "700" }}>Current assigned vehicle</Text>
            <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "900" }}>
              {[profile.assigned_vehicle.make, profile.assigned_vehicle.model, profile.assigned_vehicle.year]
                .filter(value => value !== undefined && value !== null && value !== "")
                .join(" ")}
            </Text>
            <Text style={{ color: palette.muted, fontSize: 12 }}>
              {profile.assigned_vehicle.license_plate ?? "Registration not provided"}
              {profile.assigned_vehicle.vehicle_class ? " · " + profile.assigned_vehicle.vehicle_class : ""}
            </Text>
          </View>
        ) : null}
      </Panel>

      <Panel>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
          <SectionTitle>Ride offers</SectionTitle>
          <StatusPill tone={offers.length ? "gold" : "neutral"}>
            {offers.length} {offers.length === 1 ? "offer" : "offers"}
          </StatusPill>
        </View>
        {offers.length === 0 ? (
          <EmptyState
            title={profile?.is_online ? "No live offers yet" : "Go online to receive offers"}
            description={
              profile?.is_online
                ? "Eligible ride requests will appear here. Keep this screen available while you are working."
                : "New offers appear here when your driver account is online and eligible."
            }
          />
        ) : (
          offers.map(offer => (
            <View
              key={offer.booking_reference}
              style={{
                gap: 11,
                padding: 13,
                borderRadius: 15,
                borderWidth: 1,
                borderColor: palette.border,
                backgroundColor: "#F8FBF9"
              }}
            >
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <Text style={{ color: palette.ink, fontSize: 12, fontWeight: "900" }}>
                  {offer.booking_reference}
                </Text>
                <StatusPill tone="gold">
                  {typeof offer.ttl_remaining === "number" ? offer.ttl_remaining + "s left" : "Offer"}
                </StatusPill>
              </View>
              <Text style={{ color: palette.ink, fontSize: 15, lineHeight: 21, fontWeight: "800" }}>
                {offer.pickup?.text ?? "Pickup"} → {offer.destination?.text ?? "Destination"}
              </Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 16 }}>
                <DetailRow
                  label="Fare estimate"
                  value={
                    offer.fare_estimate?.amount !== undefined
                      ? String(offer.fare_estimate.amount) + " " + (offer.fare_estimate.currency ?? "")
                      : "Not provided"
                  }
                />
                <DetailRow label="Ride class" value={offer.ride_class ?? "Not provided"} />
                <DetailRow label="Passengers" value={String(offer.passenger_count ?? 1)} />
              </View>
              {offer.vehicle ? (
                <Text style={{ color: palette.muted, fontSize: 12 }}>
                  {[offer.vehicle.make, offer.vehicle.model, offer.vehicle.license_plate].filter(Boolean).join(" · ")}
                </Text>
              ) : null}
              <View style={{ gap: 8 }}>
                <ActionButton
                  label="Accept offer"
                  disabled={busy}
                  onPress={() => respondToOffer(offer, "accept")}
                />
                <ActionButton
                  label="Decline offer"
                  disabled={busy}
                  onPress={() => respondToOffer(offer, "decline")}
                />
              </View>
            </View>
          ))
        )}
      </Panel>

      <Panel>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
          <SectionTitle>Active trip</SectionTitle>
          {activeTrip ? <StatusPill>{activeTrip.status}</StatusPill> : null}
        </View>
        {activeTrip ? (
          <>
            <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "900" }}>
              {activeTrip.booking_reference}
            </Text>
            <Text style={{ color: palette.ink, fontSize: 14, lineHeight: 20 }}>
              {activeTrip.pickup?.address ?? "Pickup"} → {activeTrip.dropoff?.address ?? "Destination"}
            </Text>
            <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>
              {activeTrip.fare_amount ?? "Fare pending"} {activeTrip.currency ?? ""}
              {" · "}{activeTrip.payment_method ?? "Payment method not provided"}
              {" · "}{activeTrip.payment_status ?? "Payment status pending"}
            </Text>
            <ActionButton
              label="Open trip workspace"
              onPress={() => router.push("/(tabs)/trips")}
            />
          </>
        ) : (
          <ServiceTile
            title="No active trip"
            description="When you accept an offer, its confirmed pickup, destination and next action will appear here."
            symbol="↗"
          />
        )}
      </Panel>
    </AppScreen>
  );
}
