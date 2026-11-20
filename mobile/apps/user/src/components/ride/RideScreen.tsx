import React, { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Keyboard } from "react-native";
import { useRouter } from "expo-router";
import * as Location from "expo-location";
import { authClient } from "../../services/api";
import { MobileAuthError } from "@afcon360/mobile-core";
import { colors, spacing } from "../../theme/tokens";
import {
  PamojaScreen as AppScreen,
  PamojaPageHeader as PageHeader,
} from "../PamojaScreen";
import { ServiceHeroAccent } from "../ServiceHeroAccent";
import { Progress } from "./Progress";
import { PlaceSearchField } from "./PlaceSearchField";
import { RideWhere } from "./RideWhere";
import { RideChoose } from "./RideChoose";
import { RideConfirm } from "./RideConfirm";
import { RideMatch } from "./RideMatch";
import { MapView } from "./MapView";
import { ServiceTypeSelector } from "./ServiceTypeSelector";
import { ScheduleSelector } from "./ScheduleSelector";
import type { Place, Quote, PaymentMethod, LocationSource, RideServiceType, Stage } from "./types";
import {
  normalizePlaceSearchQuery,
  validCoordinate,
  distanceSquared,
  formatMoney,
  friendlyError,
  validLocalSchedule,
  newIdempotencyKey,
  readPlaceSearchCache,
  writePlaceSearchCache,
  EMPTY_PLACE_SEARCH_STATE,
  validGeocodeCandidate,
  PLACE_SEARCH_CACHE_POSITIVE_TTL_MS,
  PLACE_SEARCH_CACHE_NEGATIVE_TTL_MS,
  PLACE_SEARCH_CACHE_MAX_ENTRIES,
} from "./utils";

const placeSearchCache = new Map<string, { expiresAt: number; results: any[]; attribution: string | null }>();

const BRAND = "#0E5B36";

function readCache(key: string) {
  const entry = placeSearchCache.get(key);
  if (!entry) return null;
  if (entry.expiresAt <= Date.now()) {
    placeSearchCache.delete(key);
    return null;
  }
  placeSearchCache.delete(key);
  placeSearchCache.set(key, entry);
  return entry;
}

function writeCache(key: string, results: any[], attribution: string | null) {
  placeSearchCache.delete(key);
  placeSearchCache.set(key, {
    expiresAt: Date.now() + (results.length ? PLACE_SEARCH_CACHE_POSITIVE_TTL_MS : PLACE_SEARCH_CACHE_NEGATIVE_TTL_MS),
    results,
    attribution,
  });
  while (placeSearchCache.size > PLACE_SEARCH_CACHE_MAX_ENTRIES) {
    const oldestKey = placeSearchCache.keys().next().value;
    if (oldestKey === undefined) break;
    placeSearchCache.delete(oldestKey);
  }
}

export function RideScreen() {
  const router = useRouter();
  const mapRef = useRef<any>(null);
  const mapResolveSeq = useRef({ pickup: 0, dropoff: 0 });
  const [stage, setStage] = useState<Stage>("where");
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  const [pickupText, setPickupText] = useState("");
  const [dropoffText, setDropoffText] = useState("");
  const [pickup, setPickup] = useState<Place | null>(null);
  const [dropoff, setDropoff] = useState<Place | null>(null);
  const [locationBusy, setLocationBusy] = useState(false);
  const [locationMessage, setLocationMessage] = useState<string | null>(null);
  const [reverseAttribution, setReverseAttribution] = useState<string | null>(null);

  const [serviceType, setServiceType] = useState<RideServiceType>("on_demand");
  const [vip, setVip] = useState(false);
  const [schedule, setSchedule] = useState<"now" | "later">("now");
  const [scheduledAt, setScheduledAt] = useState("");

  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [selectedQuote, setSelectedQuote] = useState<Quote | null>(null);
  const [distanceKm, setDistanceKm] = useState<number | null>(null);
  const [loadingQuotes, setLoadingQuotes] = useState(false);
  const [quoteError, setQuoteError] = useState<string | null>(null);

  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [paymentMethod, setPaymentMethod] = useState("");
  const [loadingPayments, setLoadingPayments] = useState(false);
  const [paymentError, setPaymentError] = useState<string | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey);

  const resetCommitment = useCallback(() => {
    setQuotes([]);
    setSelectedQuote(null);
    setDistanceKm(null);
    setQuoteError(null);
    setPaymentMethods([]);
    setPaymentMethod("");
    setPaymentError(null);
    setIdempotencyKey(newIdempotencyKey());
    setRequestError(null);
  }, []);

  const setResolvedPlace = useCallback((side: "pickup" | "dropoff", place: Place) => {
    if (!validCoordinate(place)) return;
    if (side === "pickup") {
      setPickup(place);
      setPickupText(place.label);
    } else {
      setDropoff(place);
      setDropoffText(place.label);
    }
    resetCommitment();
  }, [resetCommitment]);

  const reverseLabel = useCallback(async (latitude: number, longitude: number, source: "gps" | "map") => {
    const fallback = (source === "gps" ? "Current location · " : "Pinned location · ") +
      latitude.toFixed(5) + ", " + longitude.toFixed(5);
    let label = fallback;
    let provider = source === "gps" ? "device-gps" : "map-pin";
    try {
      const response = await authClient.request<{ success?: boolean; presentable?: boolean; display_name?: string | null; provider?: string; attribution?: string | null }>(
        "/geo/api/reverse?lat=" + encodeURIComponent(String(latitude)) +
        "&lon=" + encodeURIComponent(String(longitude))
      );
      if (response.success && response.presentable && response.display_name) {
        label = response.display_name;
        provider = response.provider || provider;
      }
      if (response.attribution) setReverseAttribution(response.attribution);
    } catch {
      // Reverse lookup enriches a pin label only
    }
    return { label, provider };
  }, []);

  const updateFromMap = useCallback(async (
    side: "pickup" | "dropoff",
    latitude: number,
    longitude: number
  ) => {
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude) ||
        latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return;
    const seq = ++mapResolveSeq.current[side];
    const fallback = "Pinned location · " + latitude.toFixed(5) + ", " + longitude.toFixed(5);
    setResolvedPlace(side, {
      label: fallback,
      latitude,
      longitude,
      provider: "map-pin",
      source: "map"
    });
    setLocationMessage(side === "pickup" ? "Pickup pin placed on the map." : "Destination pin placed on the map.");
    const resolved = await reverseLabel(latitude, longitude, "map");
    if (seq !== mapResolveSeq.current[side]) return;
    setResolvedPlace(side, {
      label: resolved.label,
      latitude,
      longitude,
      provider: resolved.provider,
      source: "map"
    });
  }, [reverseLabel, setResolvedPlace]);

  const handleMapMessage = useCallback((message: any) => {
    if (message.type === "map_ready") {
      setMapReady(true);
      setMapError(null);
    } else if (message.type === "map_tap") {
      let side: "pickup" | "dropoff";
      if (!pickup && !dropoff) {
        side = "pickup";
      } else if (pickup && !dropoff) {
        side = "dropoff";
      } else if (!pickup && dropoff) {
        side = "pickup";
      } else {
        const pickupDistance = distanceSquared(pickup as Place, message.latitude, message.longitude);
        const dropoffDistance = distanceSquared(dropoff as Place, message.latitude, message.longitude);
        side = pickupDistance < dropoffDistance ? "pickup" : "dropoff";
      }
      void updateFromMap(side, message.latitude, message.longitude);
    } else if (message.type === "map_drag" && message.side) {
      void updateFromMap(message.side, message.latitude, message.longitude);
    }
  }, [dropoff, pickup, updateFromMap]);

  useEffect(() => {
    if (!mapReady) return;
    const updatePin = (side: "pickup" | "dropoff", value: Place | null) => {
      const payload = JSON.stringify({ side, value: value ? {
        label: value.label,
        latitude: value.latitude,
        longitude: value.longitude,
        source: value.source
      } : null });
      mapRef.current?.injectJavaScript("window.__afconSetPin&&window.__afconSetPin(" + payload + ");true;");
    };
    updatePin("pickup", pickup);
    updatePin("dropoff", dropoff);
  }, [mapReady, pickup, dropoff]);

  const useCurrentLocation = useCallback(async () => {
    setLocationBusy(true);
    setLocationMessage("Requesting permission and locating your device…");
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) {
        setLocationMessage("Location permission was not granted. Search for a place or tap the map to set pickup.");
        return;
      }
      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced
      });
      const latitude = position.coords.latitude;
      const longitude = position.coords.longitude;
      const resolved = await reverseLabel(latitude, longitude, "gps");
      setResolvedPlace("pickup", {
        label: resolved.label,
        latitude,
        longitude,
        provider: resolved.provider,
        source: "gps"
      });
      setLocationMessage("Current location acquired and set as pickup.");
    } catch (error) {
      setLocationMessage(friendlyError(error, "Unable to get your location. Choose a pickup from search or the map."));
    } finally {
      setLocationBusy(false);
    }
  }, [reverseLabel, setResolvedPlace]);

  const swapLocations = useCallback(() => {
    const oldPickup = pickup;
    const oldDropoff = dropoff;
    setPickup(oldDropoff);
    setDropoff(oldPickup);
    setPickupText(oldDropoff?.label ?? dropoffText);
    setDropoffText(oldPickup?.label ?? pickupText);
    resetCommitment();
  }, [dropoff, dropoffText, pickup, pickupText, resetCommitment]);

  const setService = useCallback((nextService: RideServiceType, nextVip: boolean) => {
    setServiceType(nextService);
    setVip(nextVip);
    resetCommitment();
  }, [resetCommitment]);

  const loadQuotes = useCallback(async (preferredClass?: string | null) => {
    if (!pickup || !dropoff) return;
    setLoadingQuotes(true);
    setQuoteError(null);
    setQuotes([]);
    setSelectedQuote(null);
    setPaymentMethods([]);
    setPaymentMethod("");
    setPaymentError(null);
    setIdempotencyKey(newIdempotencyKey());
    try {
      const response = await authClient.request<{
        success: boolean;
        data?: { options?: Quote[]; distance_km?: number | null; note?: string; currency?: string };
      }>("/api/mobile/v1/transport/ride-options", {
        method: "POST",
        body: {
          pickup_latitude: pickup.latitude,
          pickup_longitude: pickup.longitude,
          dropoff_latitude: dropoff.latitude,
          dropoff_longitude: dropoff.longitude,
          service_type: serviceType,
          currency: "USD"
        }
      });
      let options = response.data?.options ?? [];
      if (vip) {
        options = options.filter(item =>
          item.vehicle_class === "premium" || item.vehicle_class === "luxury"
        );
      }
      setDistanceKm(response.data?.distance_km ?? null);
      setQuotes(options);
      if (!options.length) {
        setQuoteError(vip
          ? "No priced Premium or Luxury option is available for this route. Try Quick Ride or another route."
          : "AFCON360 could not calculate a fare for this route. Check the selected places and try again.");
        return;
      }
      const preferred = preferredClass
        ? options.find(item => item.vehicle_class === preferredClass)
        : undefined;
      setSelectedQuote(preferred ?? options[0]);
    } catch (error) {
      setQuoteError(friendlyError(error, "AFCON360 could not calculate fare options. Check your connection and try again."));
    } finally {
      setLoadingQuotes(false);
    }
  }, [pickup, dropoff, serviceType, vip]);

  const continueToOptions = useCallback(() => {
    if (!pickup || !dropoff) {
      Alert.alert("Choose both locations", "Select a verified pickup and destination, or place both pins on the map.");
      return;
    }
    if (schedule === "later" && !validLocalSchedule(scheduledAt)) {
      setLocationMessage("Enter a valid local pickup date and time before continuing.");
      return;
    }
    setStage("choose");
    void loadQuotes();
  }, [pickup, dropoff, schedule, scheduledAt, loadQuotes]);

  const continueToConfirm = useCallback(async () => {
    if (!selectedQuote) return;
    setStage("confirm");
    setPaymentError(null);
    setPaymentMethods([]);
    setPaymentMethod("");
    setLoadingPayments(true);
    try {
      const response = await authClient.request<{
        success: boolean;
        data?: { payment_methods?: PaymentMethod[] };
      }>("/api/mobile/v1/transport/payment-methods/options", {
        method: "POST",
        body: {
          currency: selectedQuote.currency,
          amount: selectedQuote.fare_total
        }
      });
      setPaymentMethods(response.data?.payment_methods ?? []);
      if (!(response.data?.payment_methods ?? []).some(item => item.status === "ready")) {
        setPaymentError("No payment method is currently certified and ready for this exact fare. Return to your Wallet setup or choose another available method.");
      }
    } catch (error) {
      setPaymentError(friendlyError(error, "AFCON360 could not check payment readiness. Retry before confirming."));
    } finally {
      setLoadingPayments(false);
    }
  }, [selectedQuote]);

  const requestRide = useCallback(async () => {
    if (!pickup || !dropoff || !selectedQuote || !paymentMethod || submitting) return;
    if (schedule === "later" && !validLocalSchedule(scheduledAt)) {
      setStage("where");
      setLocationMessage("Enter a valid local pickup date and time before confirming.");
      return;
    }
    const usesRequestFirstFlow = serviceType === "on_demand" && schedule === "now";
    setStage("match");
    setSubmitting(true);
    setRequestError(null);
    try {
      const endpoint = usesRequestFirstFlow
        ? "/api/mobile/v1/transport/ride-requests"
        : "/api/mobile/v1/transport/bookings";
      const response = await authClient.request<{
        success: boolean;
        booking_reference?: string;
        data?: { request_id?: string; booking_reference?: string };
      }>(endpoint, {
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
          pickup_source: pickup.source,
          dropoff_source: dropoff.source,
          pickup_geocode: pickup.source === "search" ? pickup.geocode : undefined,
          dropoff_geocode: dropoff.source === "search" ? dropoff.geocode : undefined,
          service_type: serviceType,
          vehicle_class: selectedQuote.vehicle_class,
          passenger_count: 1,
          booking_mode: schedule === "later" ? "scheduled" : "instant",
          pickup_time: schedule === "later" ? scheduledAt : undefined,
          payment_method: paymentMethod,
          currency: selectedQuote.currency,
          fare_quote_token: selectedQuote.quote_token,
          confirmed_fare_amount: String(selectedQuote.fare_total)
        }
      });
      const reference = response.booking_reference ??
        response.data?.request_id ??
        response.data?.booking_reference;
      if (!reference) {
        throw new Error("The ride was accepted but no tracking reference was returned. Reopen Activity before trying again.");
      }
      router.replace({
        pathname: "/(service)/ride-status/[reference]",
        params: {
          reference,
          kind: usesRequestFirstFlow ? "request" : "booking"
        }
      } as never);
    } catch (error) {
      setRequestError(friendlyError(
        error,
        "AFCON360 could not create the ride booking. Your Wallet has not been charged."
      ));
    } finally {
      setSubmitting(false);
    }
  }, [
    pickup, dropoff, selectedQuote, paymentMethod, submitting, schedule,
    scheduledAt, idempotencyKey, serviceType, router
  ]);

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Transport"
        title="Your ride, your game!"
        description="Book match-day shuttles, airport transfers and everyday rides through the same AFCON360 booking process available on the website."
      />

      <ServiceHeroAccent serviceKey="rides" title="Book your ride" subtitle="Pickup, destination, fare & payment" />

      <Progress stage={stage} />

      {stage === "where" && (
        <RideWhere
          pickup={pickup}
          dropoff={dropoff}
          pickupText={pickupText}
          dropoffText={dropoffText}
          serviceType={serviceType}
          vip={vip}
          schedule={schedule}
          scheduledAt={scheduledAt}
          locationBusy={locationBusy}
          locationMessage={locationMessage}
          reverseAttribution={reverseAttribution}
          mapReady={mapReady}
          mapError={mapError}
          onPickupTextChange={value => { setPickupText(value); setPickup(null); resetCommitment(); }}
          onDropoffTextChange={value => { setDropoffText(value); setDropoff(null); resetCommitment(); }}
          onPickupSelect={place => setResolvedPlace("pickup", place)}
          onDropoffSelect={place => setResolvedPlace("dropoff", place)}
          onUseCurrentLocation={useCurrentLocation}
          onSwapLocations={swapLocations}
          onServiceTypeChange={setService}
          onScheduleChange={schedule => { setSchedule(schedule); resetCommitment(); }}
          onScheduledAtChange={value => { setScheduledAt(value); resetCommitment(); }}
          onContinue={continueToOptions}
          resetCommitment={resetCommitment}
        />
      )}

      {stage === "choose" && (
        <RideChoose
          quotes={quotes}
          selectedQuote={selectedQuote}
          distanceKm={distanceKm}
          loadingQuotes={loadingQuotes}
          quoteError={quoteError}
          onQuoteSelect={quote => { setSelectedQuote(quote); setPaymentMethods([]); setPaymentMethod(""); setPaymentError(null); setIdempotencyKey(newIdempotencyKey()); }}
          onContinue={continueToConfirm}
          onBack={() => setStage("where")}
        />
      )}

      {stage === "confirm" && (
        <RideConfirm
          pickup={pickup}
          dropoff={dropoff}
          selectedQuote={selectedQuote}
          distanceKm={distanceKm}
          schedule={schedule}
          scheduledAt={scheduledAt}
          vip={vip}
          serviceType={serviceType}
          paymentMethods={paymentMethods}
          paymentMethod={paymentMethod}
          loadingPayments={loadingPayments}
          paymentError={paymentError}
          onPaymentMethodSelect={setPaymentMethod}
          onConfirm={requestRide}
          onBackToChoose={() => setStage("choose")}
          onBackToWhere={() => setStage("where")}
        />
      )}

      {stage === "match" && (
        <RideMatch requestError={requestError} />
      )}
    </AppScreen>
  );
}

export default RideScreen;