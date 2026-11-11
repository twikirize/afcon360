import React, { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Linking, Pressable, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { ActionButton, AppScreen, PageHeader, Panel, SectionTitle, StatusPill, palette } from "@afcon360/mobile-ui";
import { authClient } from "../../src/services/api";
import { MobileAuthError } from "@afcon360/mobile-core";

type Place = { label: string; latitude: number; longitude: number; provider: string; osm_type?: string; osm_id?: string | number };
type Quote = { vehicle_class: string; display_name: string; fare_total: number; currency: string; fare_breakdown?: unknown; quote_token: string; display_amount?: string; display_currency?: string };
type PaymentMethod = { code: string; label: string; status: string; status_message?: string; is_default?: boolean };

const styles = {
  input: { minHeight: 50, borderWidth: 1, borderColor: palette.border, borderRadius: 12, paddingHorizontal: 13, color: palette.ink, backgroundColor: palette.surface, fontSize: 14 } as const,
  small: { color: palette.muted, fontSize: 12, lineHeight: 18 } as const
};

function PlacePicker({ label, value, onValue, onSelect }: {
  label: string;
  value: string;
  onValue(value: string): void;
  onSelect(place: Place): void;
}) {
  const [results, setResults] = useState<Place[]>([]);
  const [loading, setLoading] = useState(false);
  const [attribution, setAttribution] = useState<string | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);

  useEffect(() => {
    if (value.trim().length < 2) {
      setResults([]);
      setAttribution(null);
      setLookupError(null);
      setLoading(false);
      return;
    }
    let active = true;
    const timer = setTimeout(() => {
      setLoading(true);
      setLookupError(null);
      authClient.request<{ success: boolean; results?: Place[]; attribution?: string | null }>(
        "/geo/api/geocode?q=" + encodeURIComponent(value.trim()) + "&limit=5"
      ).then(response => {
        if (!active) return;
        setResults(response.results ?? []);
        setAttribution(response.attribution ?? null);
      }).catch(() => {
        if (active) {
          setResults([]);
          setLookupError("Place search is temporarily unavailable. Check your connection and try again.");
        }
      }).finally(() => { if (active) setLoading(false); });
    }, 400);
    return () => { active = false; clearTimeout(timer); };
  }, [value]);

  return (
    <View style={{ gap: 8 }}>
      <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "800" }}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onValue}
        style={styles.input}
        placeholder="Search a place or address"
        placeholderTextColor={palette.muted}
        accessibilityLabel={label}
        autoCorrect={false}
        returnKeyType="search"
      />
      {loading ? <ActivityIndicator color={palette.green} /> : null}
      {lookupError ? <Text style={styles.small}>{lookupError}</Text> : null}
      {!loading && value.trim().length >= 2 && results.length === 0 && !lookupError ? <Text style={styles.small}>No matching places were found. Try a nearby landmark or a more specific address.</Text> : null}
      {results.map((place, index) => (
        <Pressable key={place.provider + ":" + place.latitude + ":" + place.longitude + ":" + index}
          accessibilityRole="button" onPress={() => { onSelect(place); setResults([]); }}
          style={{ padding: 12, borderRadius: 12, backgroundColor: palette.greenSoft, gap: 3 }}>
          <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "700" }}>{place.label}</Text>
          <Text style={styles.small}>{place.provider}</Text>
        </Pressable>
      ))}
      {attribution ? <Text style={styles.small}>{attribution}</Text> : null}
    </View>
  );
}

export default function RideScreen() {
  const router = useRouter();
  const [pickupText, setPickupText] = useState("");
  const [dropoffText, setDropoffText] = useState("");
  const [pickup, setPickup] = useState<Place | null>(null);
  const [dropoff, setDropoff] = useState<Place | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [selectedQuote, setSelectedQuote] = useState<Quote | null>(null);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [paymentMethod, setPaymentMethod] = useState("");
  const [loadingQuotes, setLoadingQuotes] = useState(false);
  const [loadingPayments, setLoadingPayments] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState(() => "mobile-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2));

  const selectPickup = (place: Place) => {
    setPickup(place);
    setPickupText(place.label);
    setQuotes([]);
    setSelectedQuote(null);
    setPaymentMethods([]);
    setPaymentMethod("");
  };
  const selectDropoff = (place: Place) => {
    setDropoff(place);
    setDropoffText(place.label);
    setQuotes([]);
    setSelectedQuote(null);
    setPaymentMethods([]);
    setPaymentMethod("");
  };

  async function openRouteInGoogleMaps() {
    if (!pickup || !dropoff) return;
    const url = new URL("https://www.google.com/maps/dir/");
    url.searchParams.set("api", "1");
    url.searchParams.set("origin", `${pickup.latitude},${pickup.longitude}`);
    url.searchParams.set("destination", `${dropoff.latitude},${dropoff.longitude}`);
    url.searchParams.set("travelmode", "driving");
    try {
      // HTTPS lets Android open Google Maps when installed or the secure
      // Google Maps website in the user's browser when it is not.
      await Linking.openURL(url.toString());
    } catch {
      Alert.alert("Could not open Google Maps", "Check that a browser or Google Maps is available on this device.");
    }
  }

  async function getQuotes() {
    if (!pickup || !dropoff) {
      Alert.alert("Choose both locations", "Select a pickup and destination from the verified place-search results.");
      return;
    }
    setLoadingQuotes(true);
    setQuotes([]);
    setSelectedQuote(null);
    setPaymentMethods([]);
    setPaymentMethod("");
    try {
      const response = await authClient.request<{ success: boolean; data?: { options?: Quote[]; note?: string } }>(
        "/api/mobile/v1/transport/ride-options",
        {
          method: "POST",
          body: {
            pickup_latitude: pickup.latitude,
            pickup_longitude: pickup.longitude,
            dropoff_latitude: dropoff.latitude,
            dropoff_longitude: dropoff.longitude,
            service_type: "on_demand",
            currency: "USD"
          }
        }
      );
      const options = response.data?.options ?? [];
      setQuotes(options);
      if (!options.length) Alert.alert("No fare options", "AFCON360 could not return a fare for this route. Check the locations and try again.");
    } catch (error) {
      Alert.alert("Fare lookup failed", error instanceof MobileAuthError ? error.message : "AFCON360 could not calculate fare options.");
    } finally {
      setLoadingQuotes(false);
    }
  }

  async function chooseQuote(quote: Quote) {
    setSelectedQuote(quote);
    setPaymentMethods([]);
    setPaymentMethod("");
    setIdempotencyKey("mobile-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2));
    setLoadingPayments(true);
    try {
      const response = await authClient.request<{ success: boolean; data?: { payment_methods?: PaymentMethod[] } }>(
        "/api/mobile/v1/transport/payment-methods/options",
        { method: "POST", body: { currency: quote.currency, amount: quote.fare_total } }
      );
      const methods = response.data?.payment_methods ?? [];
      setPaymentMethods(methods);
      const firstReady = methods.find(item => item.status === "ready" && item.is_default) ?? methods.find(item => item.status === "ready");
      if (firstReady) setPaymentMethod(firstReady.code);
      if (!firstReady) Alert.alert("No payment method ready", "Wallet has not certified a payment method for this fare. Please complete payment setup on the AFCON360 website.");
    } catch (error) {
      Alert.alert("Payment options unavailable", error instanceof MobileAuthError ? error.message : "AFCON360 could not check payment readiness.");
    } finally {
      setLoadingPayments(false);
    }
  }

  async function requestRide() {
    if (!pickup || !dropoff || !selectedQuote || !paymentMethod) return;
    setSubmitting(true);
    try {
      const response = await authClient.request<{ success: boolean; booking_reference?: string; data?: { request_id?: string } }>(
        "/api/mobile/v1/transport/ride-requests",
        {
          method: "POST",
          body: {
            idempotency_key: idempotencyKey,
            pickup: {
              latitude: pickup.latitude,
              longitude: pickup.longitude,
              address: pickup.label,
              provider: pickup.provider,
              osm_type: pickup.osm_type,
              osm_id: pickup.osm_id
            },
            dropoff: {
              latitude: dropoff.latitude,
              longitude: dropoff.longitude,
              address: dropoff.label,
              provider: dropoff.provider,
              osm_type: dropoff.osm_type,
              osm_id: dropoff.osm_id
            },
            pickup_source: "search",
            dropoff_source: "search",
            pickup_geocode: {
              label: pickup.label,
              latitude: pickup.latitude,
              longitude: pickup.longitude,
              provider: pickup.provider,
              osm_type: pickup.osm_type,
              osm_id: pickup.osm_id
            },
            dropoff_geocode: {
              label: dropoff.label,
              latitude: dropoff.latitude,
              longitude: dropoff.longitude,
              provider: dropoff.provider,
              osm_type: dropoff.osm_type,
              osm_id: dropoff.osm_id
            },
            service_type: "on_demand",
            vehicle_class: selectedQuote.vehicle_class,
            passenger_count: 1,
            booking_mode: "instant",
            payment_method: paymentMethod,
            currency: selectedQuote.currency,
            fare_quote_token: selectedQuote.quote_token,
            confirmed_fare_amount: String(selectedQuote.fare_total)
          }
        }
      );
      const reference = response.booking_reference ?? response.data?.request_id;
      if (!reference) throw new Error("The ride request was accepted but no reference was returned.");
      router.replace({ pathname: "/(service)/ride-status/[reference]", params: { reference } } as never);
    } catch (error) {
      Alert.alert("Ride request not submitted", error instanceof MobileAuthError ? error.message : error instanceof Error ? error.message : "AFCON360 could not create the ride request. Your wallet has not been charged.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppScreen>
      <PageHeader eyebrow="Transport" title="Where are you going?" description="Choose verified places, compare server-priced vehicle options, then confirm your fare and payment method before driver matching starts." />
      <Panel>
        <PlacePicker label="Pickup location" value={pickupText} onValue={value => { setPickupText(value); setPickup(null); }} onSelect={selectPickup} />
        {pickup ? <StatusPill>Pickup selected</StatusPill> : null}
        <PlacePicker label="Destination" value={dropoffText} onValue={value => { setDropoffText(value); setDropoff(null); }} onSelect={selectDropoff} />
        {dropoff ? <StatusPill>Destination selected</StatusPill> : null}
        <ActionButton label="Preview route in Google Maps" disabled={!pickup || !dropoff} onPress={() => void openRouteInGoogleMaps()} />
        <Text style={styles.small}>Opens Google Maps securely over HTTPS, or its website in your browser if the app is not installed.</Text>
        <ActionButton label={loadingQuotes ? "Calculating fares…" : "Show fare options"} disabled={!pickup || !dropoff || loadingQuotes} onPress={getQuotes} />
      </Panel>

      {quotes.length > 0 ? (
        <Panel>
          <SectionTitle>Choose your vehicle</SectionTitle>
          {quotes.map(quote => (
            <Pressable key={quote.vehicle_class} onPress={() => chooseQuote(quote)}
              style={{ borderWidth: 1, borderColor: selectedQuote?.vehicle_class === quote.vehicle_class ? palette.green : palette.border, borderRadius: 14, padding: 14, gap: 4 }}>
              <Text style={{ color: palette.ink, fontWeight: "800", fontSize: 15 }}>{quote.display_name}</Text>
              <Text style={{ color: palette.greenDark, fontSize: 17, fontWeight: "900" }}>{quote.display_amount ?? quote.fare_total.toFixed(2)} {quote.display_currency ?? quote.currency}</Text>
              <Text style={styles.small}>Signed fare quote · {quote.vehicle_class}</Text>
            </Pressable>
          ))}
        </Panel>
      ) : null}

      {selectedQuote ? (
        <Panel>
          <SectionTitle>Payment method</SectionTitle>
          {loadingPayments ? <ActivityIndicator color={palette.green} /> : paymentMethods.map(method => (
            <Pressable key={method.code} onPress={() => method.status === "ready" && setPaymentMethod(method.code)}
              style={{ borderWidth: 1, borderColor: paymentMethod === method.code ? palette.green : palette.border, borderRadius: 12, padding: 12, opacity: method.status === "ready" ? 1 : 0.55, gap: 4 }}>
              <Text style={{ color: palette.ink, fontWeight: "800" }}>{method.label}</Text>
              <Text style={styles.small}>{method.status === "ready" ? "Ready" : method.status_message ?? method.status}</Text>
            </Pressable>
          ))}
          <ActionButton label={submitting ? "Sending ride request…" : "Confirm fare and find a driver"} disabled={!paymentMethod || submitting || loadingPayments} onPress={requestRide} />
          <Text style={styles.small}>The fare is an estimate signed by AFCON360. Matching starts after the request is accepted. Payment is settled by the selected method according to Wallet rules; this step does not capture funds.</Text>
        </Panel>
      ) : null}
    </AppScreen>
  );
}
