import React, { useCallback, useRef, useState } from "react";
import { Alert, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import * as Location from "expo-location";
import { authClient } from "../../services/api";
import { MobileAuthError } from "@afcon360/mobile-core";
import { useAuth } from "../../auth/AuthProvider";
import { colors, spacing } from "../../theme/tokens";
import {
  PamojaScreen as AppScreen,
  PamojaPageHeader as PageHeader,
} from "../PamojaScreen";
import { ServiceHeroAccent } from "../ServiceHeroAccent";
import { Progress } from "./Progress";
import { RideWhere } from "./RideWhere";
import { RideChoose } from "./RideChoose";
import { RideConfirm } from "./RideConfirm";
import { RideMatch } from "./RideMatch";
import type { Place, Quote, PaymentMethod, RideServiceType, Stage } from "./types";
import {
  validCoordinate,
  distanceSquared,
  friendlyError,
  validLocalSchedule,
  newIdempotencyKey,
} from "./utils";

// A device with no satellite fix (indoors, on a desk, in a taxi) never resolves
// getCurrentPositionAsync, so pressing "Use my current location" left the screen
// on "locating…" indefinitely. Bound the wait and accept a cached fix.
const GPS_FIX_TIMEOUT_MS = 12000;
const LAST_KNOWN_FIX_MAX_AGE_MS = 2 * 60 * 1000;

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  return Promise.race([
    promise,
    new Promise<null>(resolve => setTimeout(() => resolve(null), ms)),
  ]).catch(() => null);
}

export function RideScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const mapResolveSeq = useRef({ pickup: 0, dropoff: 0 });
  const [stage, setStage] = useState<Stage>("where");

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
  const [verificationRequired, setVerificationRequired] = useState(false);
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
    setVerificationRequired(false);
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
    // "map_ready" is owned by RideWhere (it renders the map and its fallback);
    // only taps and pin drags need the screen's reverse-geocode pipeline.
    if (message.type === "map_tap") {
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

  const useCurrentLocation = useCallback(async () => {
    setLocationBusy(true);
    setLocationMessage("Requesting permission and locating your device…");
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) {
        setLocationMessage(
          permission.canAskAgain
            ? "Location permission was not granted. Search for a place or tap the map to set pickup."
            : "Location is blocked for Pamoja in Android settings. Enable it there, or search for a place or tap the map."
        );
        return;
      }

      // Prefer a recent cached fix: it is instant and accurate enough to seed a
      // pickup, while a live fix can take a minute or never arrive at all.
      const lastKnown = await Location.getLastKnownPositionAsync().catch(() => null);
      const lastKnownIsFresh = !!lastKnown && Date.now() - lastKnown.timestamp <= LAST_KNOWN_FIX_MAX_AGE_MS;

      setLocationMessage(lastKnownIsFresh ? "Using your last known location…" : "Getting a GPS fix…");
      const live = lastKnownIsFresh
        ? null
        : await withTimeout(
            Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
            GPS_FIX_TIMEOUT_MS
          );

      // A stale cached fix still beats sending the rider back to search.
      const position = live ?? lastKnown;
      if (!position) {
        setLocationMessage("No location fix yet. Search for a place or tap the map to set pickup.");
        return;
      }

      const latitude = position.coords.latitude;
      const longitude = position.coords.longitude;
      const resolved = await reverseLabel(latitude, longitude, "gps");
      if (!validCoordinate({ latitude, longitude })) {
        setLocationMessage("Your device reported an unusable position. Search for a place or tap the map to set pickup.");
        return;
      }
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
    // Discovery/commitment boundary, straight from
    // templates/transport/new_home.html: anonymous riders browse the whole
    // pre-booking flow and see real fares; Confirm requires a session.
    // This screen stays mounted behind the sign-in route, so the chosen
    // pickup, destination, class and fare survive the detour.
    if (!user) { router.push("/login" as never); return; }
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
  }, [selectedQuote, user, router]);

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
    setVerificationRequired(false);
    try {
      const endpoint = usesRequestFirstFlow
        ? "/api/mobile/v1/transport/ride-requests"
        : "/api/mobile/v1/transport/bookings";
      const response = await authClient.request<{
        success: boolean;
        code?: string;
        message?: string;
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
      // A 200 that carries success:false is a refusal, not a ride. Treating it
      // as "no reference returned" hid the server's own reason (KYC, profile)
      // behind a generic error while the rider waited for a match.
      if (response.success === false) {
        throw new MobileAuthError(
          response.message ?? "AFCON360 refused this ride request.",
          response.code ?? "ride_request_refused"
        );
      }
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
      // The commitment gate answers with a machine-readable refusal. Keep the
      // server's sentence, but mark it so the rider is told what will unblock
      // them instead of watching a match that has already been decided.
      const code = error instanceof MobileAuthError ? error.code : null;
      if (code === "kyc_upgrade_required" || code === "profile_completion_required") {
        setVerificationRequired(true);
        setRequestError(
          friendlyError(error, "AFCON360 needs more account verification before this ride can be requested.")
        );
        return;
      }
      if (code === "offline_read_only") {
        // A cached identity cannot book. Say so, instead of letting the
        // rider retry a request the client already knows will be refused.
        setRequestError(
          "You are working from saved offline information, so this ride was not sent. Reconnect to AFCON360 and try again."
        );
        return;
      }
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

  // The picker is a full screen, not a scrolling article: search on top, the
  // map filling whatever is left, and the sticky CTA below the fold-line-free
  // sheet. Uber / Go Dudu / SafeBoda make booking reachable in two taps; the
  // stacked-cards version hid the map and the CTA behind a scroll.
  if (stage === "where") {
    return (
      <SafeAreaView style={styles.whereSafe} edges={["top", "left", "right"]}>
        <View style={styles.whereHeader}>
          <Text style={styles.whereEyebrow}>TRANSPORT</Text>
          <Text accessibilityRole="header" style={styles.whereTitle}>
            Where are you going?
          </Text>
        </View>
        <View style={styles.whereProgress}>
          <Progress stage={stage} />
        </View>
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
          onMapMessage={handleMapMessage}
        />
      </SafeAreaView>
    );
  }

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Transport"
        title="Your ride, your game!"
        description="Book match-day shuttles, airport transfers and everyday rides through the same AFCON360 booking process available on the website."
      />

      <ServiceHeroAccent serviceKey="rides" title="Book your ride" subtitle="Pickup, destination, fare & payment" />

      <Progress stage={stage} />


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
        <RideMatch
          submitting={submitting}
          requestError={requestError}
          verificationRequired={verificationRequired}
          onRetry={requestRide}
          onChangeRide={() => setStage("choose")}
        />
      )}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  whereSafe: { flex: 1, backgroundColor: colors.surface.canvas },
  whereProgress: { paddingHorizontal: 12 },
  whereHeader: {
    paddingHorizontal: 18,
    paddingTop: spacing.sm,
    paddingBottom: 2,
  },
  whereEyebrow: {
    color: colors.brand.dark,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.35,
  },
  whereTitle: {
    color: colors.text.ink,
    fontFamily: "serif",
    fontSize: 20,
    lineHeight: 25,
    fontWeight: "700",
  },
});

export default RideScreen;