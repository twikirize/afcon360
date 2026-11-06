import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";
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

  const load = useCallback(async () => {
    try {
      const [me, offerResponse, tripResponse] = await Promise.all([
        authClient.request<{ data: DriverProfile }>("/api/mobile/v1/driver/me"),
        authClient.request<{ data: { offers: Offer[] } }>("/api/mobile/v1/driver/offers"),
        authClient.request<{ data: ActiveTrip | null }>("/api/mobile/v1/driver/trips/active")
      ]);
      setProfile(me.data);
      setOffers(offerResponse.data.offers ?? []);
      setActiveTrip(tripResponse.data ?? null);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Driver information could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    // Polling is a fallback until a supported live-delivery channel is available.
    // Keep the interval moderate so the dashboard does not over-poll the API.
    const interval = setInterval(() => { void load(); }, 10000);
    return () => clearInterval(interval);
  }, [load]);

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
