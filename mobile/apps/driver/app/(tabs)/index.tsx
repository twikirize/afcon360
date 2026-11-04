import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Pressable, Text, View } from "react-native";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, StatusPill, ActionButton, palette } from "@afcon360/mobile-ui";
import { authClient } from "../../src/services/api";
import { requestForegroundDriverLocation } from "../../src/location/permissions";
import { MobileAuthError } from "@afcon360/mobile-core";

type DriverProfile = { driver_code: string; verification_tier: string; compliance_status: string; is_online: boolean; is_available: boolean; go_live: { ready: boolean; items?: Array<{ label?: string; requirement?: string; complete?: boolean }> } };
type Offer = { booking_reference: string; status: string; ttl_remaining?: number; pickup?: { text?: string }; destination?: { text?: string }; fare_estimate?: { amount?: number; currency?: string }; ride_class?: string; passenger_count?: number; vehicle?: { make?: string; model?: string; license_plate?: string } };
type ActiveTrip = { booking_reference: string; status: string; pickup?: { address?: string }; dropoff?: { address?: string }; payment_method?: string; payment_status?: string; fare_amount?: string; currency?: string };

export default function DriverHome() {
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

  useEffect(() => { void load(); }, [load]);

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
      Alert.alert("Availability not changed", e instanceof MobileAuthError ? e.message : "AFCON360 could not update driver availability. Review your go-live checklist.");
    } finally {
      setBusy(false);
    }
  }

  async function sendLocation() {
    setBusy(true);
    try {
      const result = await requestForegroundDriverLocation();
      if (!result.granted) {
        Alert.alert("Location permission needed", "Allow location while using AFCON360 Driver to share your current position.");
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
      Alert.alert("Location not updated", e instanceof Error ? e.message : "AFCON360 could not publish your location.");
    } finally {
      setBusy(false);
    }
  }

  async function respondToOffer(offer: Offer, action: "accept" | "decline") {
    setBusy(true);
    try {
      const path = action === "accept" ? "accept" : "decline";
      await authClient.request("/api/mobile/v1/driver/offers/" + encodeURIComponent(offer.booking_reference) + "/" + path, { method: "POST", body: {} });
      Alert.alert(action === "accept" ? "Ride accepted" : "Offer declined", action === "accept" ? "AFCON360 has confirmed the driver assignment." : "This offer has been declined.");
      await load();
    } catch (e) {
      Alert.alert("Offer response not accepted", e instanceof MobileAuthError ? e.message : "This offer may have expired or been assigned elsewhere.");
      await load();
    } finally {
      setBusy(false);
    }
  }

  return <AppScreen>
    <PageHeader eyebrow="AFCON360 Driver" title="Your driving workspace." description="Availability, live offers and active trip state come from AFCON360 Transport." />
    <Panel>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <SectionTitle>Availability</SectionTitle>
        <StatusPill tone={profile?.is_online ? "green" : "gold"}>{profile?.is_online ? "Online" : "Offline"}</StatusPill>
      </View>
      {loading ? <ActivityIndicator color={palette.green} /> : null}
      {error ? <Text style={{ color: "#9A3A2F", fontSize: 13 }}>{error}</Text> : null}
      {profile ? (
        <>
          <Text style={{ color: palette.ink, fontWeight: "800" }}>Driver {profile.driver_code}</Text>
          <Text style={{ color: palette.muted, fontSize: 12 }}>Verification: {profile.verification_tier} · Compliance: {profile.compliance_status}</Text>
          <ActionButton label={busy ? "Updating…" : profile.is_online ? "Go offline" : "Go online"} disabled={busy} onPress={toggleOnline} />
          {!profile.go_live?.ready && !profile.is_online ? (
            <View style={{ gap: 4 }}>
              <Text style={{ fontWeight: "800", color: palette.ink }}>Go-live requirements</Text>
              {(profile.go_live?.items ?? []).map((item, index) => <Text key={index} style={{ color: palette.muted, fontSize: 12 }}>• {item.label ?? item.requirement ?? "Requirement"}: {item.complete ? "Complete" : "Action required"}</Text>)}
            </View>
          ) : null}
          <ActionButton label={busy ? "Please wait…" : "Share current location"} disabled={busy || !profile.is_online} onPress={sendLocation} />
          <Text style={{ color: palette.muted, fontSize: 11 }}>Location is requested only when you tap the button. Background tracking is not enabled.</Text>
        </>
      ) : null}
      <Pressable onPress={() => { setLoading(true); void load(); }}><Text style={{ color: palette.greenDark, fontWeight: "800" }}>Refresh driver status</Text></Pressable>
    </Panel>

    <Panel>
      <SectionTitle>Ride offers</SectionTitle>
      {offers.length === 0 ? <ServiceTile title="No live offers" description="New offers appear here while your driver account is online and eligible." symbol="🔔" /> : offers.map(offer => (
        <View key={offer.booking_reference} style={{ borderTopWidth: 1, borderTopColor: palette.border, paddingTop: 12, gap: 6 }}>
          <StatusPill tone="gold">Offer · {offer.ttl_remaining ?? 0}s left</StatusPill>
          <Text style={{ color: palette.ink, fontWeight: "800" }}>{offer.pickup?.text ?? "Pickup"} → {offer.destination?.text ?? "Destination"}</Text>
          <Text style={{ color: palette.ink }}>{offer.fare_estimate?.amount ?? "—"} {offer.fare_estimate?.currency ?? ""} · {offer.ride_class ?? "Vehicle"} · {offer.passenger_count ?? 1} passenger(s)</Text>
          {offer.vehicle ? <Text style={{ color: palette.muted }}>{[offer.vehicle.make, offer.vehicle.model, offer.vehicle.license_plate].filter(Boolean).join(" ")}</Text> : null}
          <View style={{ flexDirection: "row", gap: 9 }}>
            <View style={{ flex: 1 }}><ActionButton label="Accept offer" disabled={busy} onPress={() => respondToOffer(offer, "accept")} /></View>
            <View style={{ flex: 1 }}><ActionButton label="Decline" disabled={busy} onPress={() => respondToOffer(offer, "decline")} /></View>
          </View>
        </View>
      ))}
    </Panel>

    <Panel>
      <SectionTitle>Active trip</SectionTitle>
      {activeTrip ? (
        <>
          <StatusPill>{activeTrip.status}</StatusPill>
          <Text style={{ color: palette.ink, fontWeight: "800" }}>{activeTrip.booking_reference}</Text>
          <Text style={{ color: palette.muted }}>{activeTrip.pickup?.address ?? "Pickup"} → {activeTrip.dropoff?.address ?? "Destination"}</Text>
          <Text style={{ color: palette.ink }}>{activeTrip.fare_amount ?? "—"} {activeTrip.currency ?? ""} · {activeTrip.payment_method ?? "Payment"} · {activeTrip.payment_status ?? "Pending"}</Text>
        </>
      ) : <ServiceTile title="No active trip" description="Accepted assignments and in-progress rides appear here." symbol="🧭" />}
    </Panel>
  </AppScreen>;
}
