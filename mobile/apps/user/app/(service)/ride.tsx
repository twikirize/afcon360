import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Keyboard,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import { useRouter } from "expo-router";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import * as Location from "expo-location";
import {
  ActionButton,
  AppScreen,
  PageHeader,
  Panel,
  SectionTitle,
  StatusPill,
  palette
} from "@afcon360/mobile-ui";
import { authClient } from "../../src/services/api";
import { MobileAuthError } from "@afcon360/mobile-core";

type LocationSource = "search" | "gps" | "map";

type GeocodeCandidate = {
  label: string;
  latitude: number;
  longitude: number;
  provider: string;
  osm_type?: string;
  osm_id?: string | number;
};

type Place = GeocodeCandidate & {
  source: LocationSource;
  geocode?: GeocodeCandidate;
};

type PlaceSearchStatus = "idle" | "loading" | "success" | "error";

type PlaceSearchState = {
  query: string;
  status: PlaceSearchStatus;
  results: GeocodeCandidate[];
  attribution: string | null;
  error: string | null;
};

type PlaceSearchCacheEntry = {
  expiresAt: number;
  results: GeocodeCandidate[];
  attribution: string | null;
};

const PLACE_SEARCH_CACHE_POSITIVE_TTL_MS = 24 * 60 * 60 * 1000;
const PLACE_SEARCH_CACHE_NEGATIVE_TTL_MS = 5 * 60 * 1000;
const PLACE_SEARCH_CACHE_MAX_ENTRIES = 80;
const placeSearchCache = new Map<string, PlaceSearchCacheEntry>();

function normalizePlaceSearchQuery(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function readPlaceSearchCache(key: string): PlaceSearchCacheEntry | null {
  const entry = placeSearchCache.get(key);
  if (!entry) return null;
  if (entry.expiresAt <= Date.now()) {
    placeSearchCache.delete(key);
    return null;
  }
  // Refresh insertion order so frequently used searches stay in the bounded cache.
  placeSearchCache.delete(key);
  placeSearchCache.set(key, entry);
  return entry;
}

function writePlaceSearchCache(
  key: string,
  results: GeocodeCandidate[],
  attribution: string | null
): void {
  placeSearchCache.delete(key);
  placeSearchCache.set(key, {
    expiresAt: Date.now() + (results.length
      ? PLACE_SEARCH_CACHE_POSITIVE_TTL_MS
      : PLACE_SEARCH_CACHE_NEGATIVE_TTL_MS),
    results,
    attribution
  });
  while (placeSearchCache.size > PLACE_SEARCH_CACHE_MAX_ENTRIES) {
    const oldestKey = placeSearchCache.keys().next().value;
    if (oldestKey === undefined) break;
    placeSearchCache.delete(oldestKey);
  }
}

const EMPTY_PLACE_SEARCH_STATE: PlaceSearchState = {
  query: "",
  status: "idle",
  results: [],
  attribution: null,
  error: null
};

function validGeocodeCandidate(value: unknown): value is GeocodeCandidate {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<GeocodeCandidate>;
  return typeof candidate.label === "string" && candidate.label.trim().length > 0 &&
    typeof candidate.provider === "string" && candidate.provider.trim().length > 0 &&
    typeof candidate.latitude === "number" && Number.isFinite(candidate.latitude) &&
    candidate.latitude >= -90 && candidate.latitude <= 90 &&
    typeof candidate.longitude === "number" && Number.isFinite(candidate.longitude) &&
    candidate.longitude >= -180 && candidate.longitude <= 180;
}

type Quote = {
  vehicle_class: string;
  display_name: string;
  fare_total: number;
  currency: string;
  fare_breakdown?: {
    base_fare?: number;
    distance_charge?: number;
    class_multiplier?: number;
    surge_multiplier?: number;
    [key: string]: unknown;
  };
  quote_token: string;
  display_amount?: number;
  display_currency?: string;
  display_rate?: number;
  display_is_approximate?: boolean;
  display_rate_at?: string | null;
  display_rate_attribution_url?: string | null;
};

type PaymentMethod = {
  code: string;
  label: string;
  status: string;
  status_message?: string;
  is_default?: boolean;
};

type MapMessage =
  | { type: "map_ready" }
  | { type: "map_tap" | "map_drag"; latitude: number; longitude: number; side?: "pickup" | "dropoff" };

type ReverseResponse = {
  success?: boolean;
  presentable?: boolean;
  display_name?: string | null;
  provider?: string;
  attribution?: string | null;
};

type Stage = "where" | "choose" | "confirm" | "match";

const BRAND = "#0E6B4F";
const BRAND_DARK = "#0A4E3A";
const BRAND_SOFT = "#E6F2ED";
const YELLOW = "#F6C744";
const INK = "#0C1512";
const MUTED = "#77857F";
const LINE = "#E2E8E4";
const RED = "#B42318";

const MAP_HTML = [
  "<!doctype html>",
  "<html><head><meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no'>",
  "<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css'>",
  "<style>html,body,#map{height:100%;width:100%;margin:0;background:#e9f0eb} .leaflet-container{font:13px sans-serif} .pin{width:22px;height:22px;border:3px solid white;border-radius:50%;box-shadow:0 2px 7px #0006} .pin.pickup{background:#0e6b4f} .pin.dropoff{background:#d92d20} .leaflet-control-attribution{font-size:9px!important}</style>",
  "<script src='https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js'></script>",
  "</head><body><div id='map'></div>",
  "<script>",
  "(function(){",
  "  var map=L.map('map',{zoomControl:true,attributionControl:true}).setView([0.3136,32.5811],12);",
  "  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors'}).addTo(map);",
  "  var pins={pickup:null,dropoff:null},line=null;",
  "  function send(value){if(window.ReactNativeWebView)window.ReactNativeWebView.postMessage(JSON.stringify(value));}",
  "  function icon(side){return L.divIcon({className:'',html:'<div class=\"pin '+side+'\"></div>',iconSize:[22,22],iconAnchor:[11,11]});}",
  "  function refresh(){if(line){map.removeLayer(line);line=null;} var p=pins.pickup,d=pins.dropoff; if(p&&d){line=L.polyline([[p.lat,p.lng],[d.lat,d.lng]],{color:'#0e6b4f',weight:4,dashArray:'8 8',opacity:.9}).addTo(map);map.fitBounds(line.getBounds(),{padding:[34,34],maxZoom:15});}else if(p){map.setView([p.lat,p.lng],15);}else if(d){map.setView([d.lat,d.lng],15);}}",
  "  window.__afconSetPin=function(p){var side=p.side;if(!side)return;if(!p.value){if(pins[side])map.removeLayer(pins[side]);pins[side]=null;refresh();return;}var v=p.value;if(pins[side]){pins[side].setLatLng([v.latitude,v.longitude]);}else{pins[side]=L.marker([v.latitude,v.longitude],{draggable:true,icon:icon(side)}).addTo(map);pins[side].on('dragend',function(){var ll=pins[side].getLatLng();send({type:'map_drag',side:side,latitude:ll.lat,longitude:ll.lng});});}refresh();};",
  "  map.on('click',function(e){send({type:'map_tap',latitude:e.latlng.lat,longitude:e.latlng.lng});});",
  "  setTimeout(function(){map.invalidateSize();send({type:'map_ready'});},250);",
  "})();",
  "</script></body></html>"
].join("\n");

function newIdempotencyKey() {
  return "mobile-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
}

function validCoordinate(place: Pick<Place, "latitude" | "longitude">): boolean {
  return Number.isFinite(place.latitude) &&
    Number.isFinite(place.longitude) &&
    place.latitude >= -90 && place.latitude <= 90 &&
    place.longitude >= -180 && place.longitude <= 180;
}

function distanceSquared(a: Place, latitude: number, longitude: number): number {
  const latScale = Math.cos(latitude * Math.PI / 180);
  const x = (a.longitude - longitude) * latScale;
  const y = a.latitude - latitude;
  return x * x + y * y;
}

function formatMoney(amount: number, currency: string): string {
  const code = (currency || "USD").toUpperCase();
  const digits = ["UGX", "RWF", "JPY", "KRW", "VND"].includes(code) ? 0 : 2;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: code,
      currencyDisplay: "code",
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    }).format(Number(amount || 0));
  } catch {
    return code + " " + Number(amount || 0).toFixed(digits);
  }
}

function friendlyError(error: unknown, fallback: string): string {
  if (error instanceof MobileAuthError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}

function validLocalSchedule(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value || "");
  if (!match) return false;
  const date = new Date(Date.UTC(
    Number(match[1]), Number(match[2]) - 1, Number(match[3]),
    Number(match[4]), Number(match[5])
  ));
  return date.getUTCFullYear() === Number(match[1]) &&
    date.getUTCMonth() === Number(match[2]) - 1 &&
    date.getUTCDate() === Number(match[3]) &&
    date.getUTCHours() === Number(match[4]) &&
    date.getUTCMinutes() === Number(match[5]);
}

function PlaceSearchField({
  label,
  value,
  placeholder,
  onValue,
  onSelect
}: {
  label: string;
  value: string;
  placeholder: string;
  onValue(value: string): void;
  onSelect(place: Place): void;
}) {
  const [searchState, setSearchState] = useState<PlaceSearchState>(EMPTY_PLACE_SEARCH_STATE);
  const selectedLabelQuery = useRef<string | null>(null);
  const query = value.trim().replace(/\s+/g, " ");
  const queryKey = normalizePlaceSearchQuery(query);
  // Never flash suggestions from the previous input while the next effect starts.
  const visibleState = searchState.query === queryKey
    ? searchState
    : { ...EMPTY_PLACE_SEARCH_STATE, query: queryKey };

  useEffect(() => {
    if (query.length < 2) {
      setSearchState({ ...EMPTY_PLACE_SEARCH_STATE, query: queryKey });
      return;
    }

    // Choosing a provider result changes the field to its canonical full label.
    // Do not immediately run a second search for the label we just selected.
    if (selectedLabelQuery.current === queryKey) {
      selectedLabelQuery.current = null;
      setSearchState({ ...EMPTY_PLACE_SEARCH_STATE, query: queryKey });
      return;
    }

    const cached = readPlaceSearchCache(queryKey);
    if (cached) {
      setSearchState({
        query: queryKey,
        status: "success",
        results: cached.results,
        attribution: cached.attribution,
        error: null
      });
      return;
    }

    let active = true;
    const controller = new AbortController();
    setSearchState({
      query: queryKey,
      status: "loading",
      results: [],
      attribution: null,
      error: null
    });

    const timer = setTimeout(() => {
      void authClient.request<{
        success?: boolean;
        results?: unknown[];
        attribution?: string | null;
      }>(
        "/geo/api/geocode?q=" + encodeURIComponent(query) + "&limit=5",
        { signal: controller.signal }
      ).then(response => {
        if (!active) return;
        if (response.success !== true || !Array.isArray(response.results)) {
          throw new Error("AFCON360 could not read the place-search results. Search again.");
        }

        const candidates = response.results.filter(validGeocodeCandidate);
        if (response.results.length > 0 && candidates.length === 0) {
          throw new Error("AFCON360 could not verify the returned place results. Search again.");
        }

        const attribution = typeof response.attribution === "string"
          ? response.attribution
          : null;
        writePlaceSearchCache(queryKey, candidates, attribution);
        setSearchState({
          query: queryKey,
          status: "success",
          results: candidates,
          attribution,
          error: null
        });
      }).catch(error => {
        if (!active || controller.signal.aborted) return;
        setSearchState({
          query: queryKey,
          status: "error",
          results: [],
          attribution: null,
          error: friendlyError(
            error,
            "Place search is temporarily unavailable. Check your connection and try again."
          )
        });
      });
    }, 300);

    return () => {
      active = false;
      clearTimeout(timer);
      // A new query or unmount cancels the previous network request, not just its UI update.
      controller.abort();
    };
  }, [query, queryKey]);

  const selectCandidate = (candidate: GeocodeCandidate) => {
    // Keep the exact server candidate as evidence; add app-only provenance separately.
    const geocode = { ...candidate };
    selectedLabelQuery.current = normalizePlaceSearchQuery(candidate.label);
    setSearchState({ ...EMPTY_PLACE_SEARCH_STATE, query: selectedLabelQuery.current });
    onSelect({ ...geocode, source: "search", geocode });
    Keyboard.dismiss();
  };

  return (
    <View style={styles.fieldGroup}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={nextValue => {
          selectedLabelQuery.current = null;
          onValue(nextValue);
        }}
        onSubmitEditing={() => {
          if (visibleState.status === "success" && visibleState.results[0]) {
            selectCandidate(visibleState.results[0]);
          }
        }}
        style={styles.input}
        placeholder={placeholder}
        placeholderTextColor={MUTED}
        accessibilityLabel={label}
        accessibilityHint="Enter at least two characters, then choose a verified place from the suggestions."
        autoCorrect={false}
        returnKeyType="search"
      />
      {visibleState.status === "loading" ? (
        <View style={styles.searchStatus}>
          <ActivityIndicator color={BRAND} />
          <Text style={styles.helperText}>Searching AFCON360 places…</Text>
        </View>
      ) : null}
      {visibleState.status === "error" ? (
        <Text style={styles.errorText} accessibilityLiveRegion="polite">
          {visibleState.error ?? "Place search is temporarily unavailable. Check your connection and try again."}
        </Text>
      ) : null}
      {visibleState.status === "success" && visibleState.results.length === 0 ? (
        <Text style={styles.helperText} accessibilityLiveRegion="polite">
          No matching places were found. Try a nearby landmark or a more specific address.
        </Text>
      ) : null}
      {visibleState.status === "success" && visibleState.results.length > 0 ? (
        <View style={styles.searchResults}>
          {visibleState.results.map((place, index) => (
            <Pressable
              key={place.provider + ":" + (place.osm_type ?? "") + ":" +
                (place.osm_id ?? place.latitude + "," + place.longitude) + ":" + index}
              accessibilityRole="button"
              accessibilityLabel={place.label}
              accessibilityHint={"Select this result as your " + label.toLowerCase() + "."}
              onPress={() => selectCandidate(place)}
              style={styles.searchResult}
            >
              <Text style={styles.searchResultTitle}>{place.label}</Text>
              <Text style={styles.helperText}>{place.provider}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
      {visibleState.status === "success" && visibleState.attribution ? (
        <Text style={styles.attribution}>{visibleState.attribution}</Text>
      ) : null}
    </View>
  );
}

function Progress({ stage }: { stage: Stage }) {
  const names: { key: Stage; label: string }[] = [
    { key: "where", label: "Where" },
    { key: "choose", label: "Choose" },
    { key: "confirm", label: "Confirm" },
    { key: "match", label: "Match" }
  ];
  const current = names.findIndex(item => item.key === stage);
  return (
    <View style={styles.progress}>
      {names.map((item, index) => (
        <React.Fragment key={item.key}>
          <View style={styles.progressStep}>
            <View style={[
              styles.progressNumber,
              index < current ? styles.progressDone : null,
              index === current ? styles.progressActive : null
            ]}>
              <Text style={[
                styles.progressNumberText,
                index <= current ? styles.progressNumberTextActive : null
              ]}>{index < current ? "✓" : String(index + 1)}</Text>
            </View>
            <Text style={[styles.progressLabel, index <= current ? styles.progressLabelActive : null]}>
              {item.label}
            </Text>
          </View>
          {index < names.length - 1 ? (
            <View style={[styles.progressLine, index < current ? styles.progressLineDone : null]} />
          ) : null}
        </React.Fragment>
      ))}
    </View>
  );
}

export default function RideScreen() {
  const router = useRouter();
  const mapRef = useRef<WebView>(null);
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

  const [serviceType, setServiceType] = useState("on_demand");
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
      const response = await authClient.request<ReverseResponse>(
        "/geo/api/reverse?lat=" + encodeURIComponent(String(latitude)) +
        "&lon=" + encodeURIComponent(String(longitude))
      );
      if (response.success && response.presentable && response.display_name) {
        label = response.display_name;
        provider = response.provider || provider;
      }
      if (response.attribution) setReverseAttribution(response.attribution);
    } catch {
      // Reverse lookup enriches a pin label only. The original coordinates and
      // GPS/map provenance remain authoritative even when a provider is offline.
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
    // Commit the coordinates immediately so a fast second map tap can
    // resolve to the other endpoint while reverse geocoding is still pending.
    setResolvedPlace(side, {
      label: fallback,
      latitude,
      longitude,
      provider: "map-pin",
      source: "map"
    });
    setLocationMessage(side === "pickup" ? "Pickup pin placed on the map." : "Destination pin placed on the map.");
    const resolved = await reverseLabel(latitude, longitude, "map");
    // A slow response must not overwrite a newer pin on the same side.
    if (seq !== mapResolveSeq.current[side]) return;
    setResolvedPlace(side, {
      label: resolved.label,
      latitude,
      longitude,
      provider: resolved.provider,
      source: "map"
    });
  }, [reverseLabel, setResolvedPlace]);

  const handleMapMessage = useCallback((event: WebViewMessageEvent) => {
    try {
      const message = JSON.parse(event.nativeEvent.data) as MapMessage;
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
    } catch {
      setMapError("The map returned an unreadable location. Use place search or GPS instead.");
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

  const setService = useCallback((nextService: string, nextVip: boolean) => {
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
    setStage("match");
    setSubmitting(true);
    setRequestError(null);
    try {
      const response = await authClient.request<{
        success: boolean;
        booking_reference?: string;
        data?: { request_id?: string };
      }>("/api/mobile/v1/transport/ride-requests", {
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
      const reference = response.booking_reference ?? response.data?.request_id;
      if (!reference) {
        throw new Error("The ride request was accepted but no tracking reference was returned. Reopen Activity before trying again.");
      }
      router.replace({
        pathname: "/(service)/ride-status/[reference]",
        params: { reference }
      } as never);
    } catch (error) {
      setRequestError(friendlyError(error, "AFCON360 could not create the ride request. Your Wallet has not been charged."));
    } finally {
      setSubmitting(false);
    }
  }, [
    pickup, dropoff, selectedQuote, paymentMethod, submitting, schedule,
    scheduledAt, idempotencyKey, serviceType, router
  ]);

  const fmtSchedule = schedule === "later" ? scheduledAt.replace("T", " ") : "Leaving now";
  const displayCurrency = selectedQuote?.display_currency ?? selectedQuote?.currency ?? "USD";
  const displayAmount = selectedQuote?.display_amount ?? selectedQuote?.fare_total ?? 0;
  const displayApprox = selectedQuote?.display_is_approximate === true;
  const breakdown = selectedQuote?.fare_breakdown;

  const displayBreakdown = (amount: unknown) => {
    const numeric = Number(amount ?? 0);
    const rate = Number(selectedQuote?.display_rate ?? 1);
    return formatMoney(numeric * (Number.isFinite(rate) && rate > 0 ? rate : 1), displayCurrency);
  };

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Transport"
        title="Your ride, your game!"
        description="Book match-day shuttles, airport transfers and everyday rides through the same AFCON360 booking process available on the website."
      />

      <Progress stage={stage} />

      {stage === "where" ? (
        <>
          <Panel>
            <SectionTitle>Where are you going?</SectionTitle>
            <View style={styles.routeRow}>
              <View style={styles.routeFields}>
                <PlaceSearchField
                  label="Pickup location"
                  value={pickupText}
                  placeholder="Current location or search an address"
                  onValue={value => {
                    setPickupText(value);
                    setPickup(null);
                    resetCommitment();
                  }}
                  onSelect={place => setResolvedPlace("pickup", place)}
                />
                {pickup ? (
                  <Text style={styles.sourceText}>
                    {pickup.source === "gps" ? "Current device location" :
                      pickup.source === "map" ? "Selected on map" : "Verified place-search result"}
                  </Text>
                ) : null}
                <Pressable
                  accessibilityRole="button"
                  disabled={locationBusy}
                  onPress={() => void useCurrentLocation()}
                  style={[styles.locationButton, locationBusy ? styles.disabled : null]}
                >
                  {locationBusy ? <ActivityIndicator color={BRAND} /> : <Text style={styles.locationButtonText}>◎  Use my current location</Text>}
                </Pressable>

                <PlaceSearchField
                  label="Destination"
                  value={dropoffText}
                  placeholder="Enter destination"
                  onValue={value => {
                    setDropoffText(value);
                    setDropoff(null);
                    resetCommitment();
                  }}
                  onSelect={place => setResolvedPlace("dropoff", place)}
                />
                {dropoff ? (
                  <Text style={styles.sourceText}>
                    {dropoff.source === "gps" ? "Current device location" :
                      dropoff.source === "map" ? "Selected on map" : "Verified place-search result"}
                  </Text>
                ) : null}
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Swap pickup and destination"
                onPress={swapLocations}
                style={styles.swapButton}
              >
                <Text style={styles.swapText}>↕</Text>
              </Pressable>
            </View>

            <Text style={styles.label}>Popular destinations</Text>
            <View style={styles.chips}>
              {[
                "Mandela National Stadium, Namboole",
                "Lugogo Cricket Oval, Kampala",
                "Nile Independence Stadium"
              ].map((name, index) => (
                <Pressable
                  key={name}
                  onPress={() => {
                    setDropoffText(name);
                    setDropoff(null);
                    resetCommitment();
                  }}
                  style={styles.chip}
                >
                  <Text style={styles.chipText}>{["Namboole Stadium", "Lugogo Oval", "Nile Independence"][index]}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.label}>Service type</Text>
            <View style={styles.serviceRow}>
              <Pressable
                onPress={() => setService("on_demand", false)}
                style={[styles.serviceChoice, serviceType === "on_demand" && !vip ? styles.serviceSelected : null]}
              >
                <Text style={styles.serviceIcon}>◷</Text>
                <Text style={styles.serviceName}>Quick Ride</Text>
              </Pressable>
              <Pressable
                onPress={() => setService("airport_departure", false)}
                style={[styles.serviceChoice, serviceType === "airport_departure" ? styles.serviceAirportSelected : null]}
              >
                <Text style={styles.serviceIcon}>✈</Text>
                <Text style={styles.serviceName}>Airport Transfer</Text>
              </Pressable>
              <Pressable
                onPress={() => setService("on_demand", true)}
                style={[styles.serviceChoice, vip ? styles.serviceVipSelected : null]}
              >
                <Text style={styles.serviceIcon}>★</Text>
                <Text style={styles.serviceName}>VIP Service</Text>
              </Pressable>
            </View>

            <Text style={styles.label}>When do you need the ride?</Text>
            <View style={styles.scheduleRow}>
              <Pressable
                onPress={() => {
                  setSchedule("now");
                  resetCommitment();
                }}
                style={[styles.scheduleChoice, schedule === "now" ? styles.scheduleSelected : null]}
              >
                <Text style={styles.scheduleText}>⚡  Now</Text>
              </Pressable>
              <Pressable
                onPress={() => {
                  setSchedule("later");
                  resetCommitment();
                }}
                style={[styles.scheduleChoice, schedule === "later" ? styles.scheduleSelected : null]}
              >
                <Text style={styles.scheduleText}>▦  Later</Text>
              </Pressable>
            </View>
            {schedule === "later" ? (
              <>
                <TextInput
                  value={scheduledAt}
                  onChangeText={value => {
                    setScheduledAt(value);
                    resetCommitment();
                  }}
                  style={styles.input}
                  placeholder="YYYY-MM-DDTHH:mm"
                  placeholderTextColor={MUTED}
                  accessibilityLabel="Scheduled local pickup date and time"
                  autoCapitalize="none"
                />
                <Text style={styles.helperText}>Enter the pickup location's local time. AFCON360 resolves its timezone and enforces the 15-minute minimum lead time on the server.</Text>
              </>
            ) : null}

            {locationMessage ? <Text style={styles.helperText}>{locationMessage}</Text> : null}
            {reverseAttribution ? <Text style={styles.attribution}>{reverseAttribution}</Text> : null}

            <ActionButton
              label="See Ride Options"
              disabled={!pickup || !dropoff || (schedule === "later" && !validLocalSchedule(scheduledAt))}
              onPress={continueToOptions}
            />
            <Text style={styles.helperText}>Choose both locations by verified search, GPS or the map before requesting a fare.</Text>
          </Panel>

          <Panel>
            <SectionTitle>Choose pickup and destination on the map</SectionTitle>
            <Text style={styles.helperText}>Tap once to place pickup, then tap again for destination. Drag either pin to adjust it. When both pins are set, tapping near one moves that pin.</Text>
            <View style={styles.mapFrame}>
              <WebView
                ref={mapRef}
                source={{ html: MAP_HTML, baseUrl: "https://www.openstreetmap.org" }}
                originWhitelist={["*"]}
                javaScriptEnabled
                domStorageEnabled
                scrollEnabled={false}
                nestedScrollEnabled={false}
                onMessage={handleMapMessage}
                onLoadEnd={() => setMapError(null)}
                onError={() => setMapError("The map could not load. Place search and device GPS remain available.")}
                onHttpError={() => setMapError("Map tiles are temporarily unavailable. Place search and device GPS remain available.")}
                style={styles.map}
              />
            </View>
            {!mapReady ? (
              <View style={styles.mapOverlay}>
                <ActivityIndicator color={BRAND} />
                <Text style={styles.helperText}>Loading map…</Text>
              </View>
            ) : null}
            {mapError ? <Text style={styles.errorText}>{mapError}</Text> : null}
            <Text style={styles.attribution}>Map data © OpenStreetMap contributors. Distance is a straight-line estimate, not road distance.</Text>
            <View style={styles.selectedRoute}>
              <Text style={styles.selectedRouteText}>Pickup: {pickup?.label ?? "Not selected"}</Text>
              <Text style={styles.selectedRouteText}>Destination: {dropoff?.label ?? "Not selected"}</Text>
            </View>
          </Panel>
        </>
      ) : null}

      {stage === "choose" ? (
        <Panel>
          <SectionTitle>Choose a vehicle class</SectionTitle>
          <Text style={styles.helperText}>
            {distanceKm != null ? "About " + Number(distanceKm).toFixed(1) + " km · " : ""}
            Fare estimates only. Driver matching has not started.
          </Text>
          {loadingQuotes ? <ActivityIndicator color={BRAND} size="large" /> : null}
          {quoteError ? <Text style={styles.errorText}>{quoteError}</Text> : null}
          {quotes.map(quote => {
            const selected = selectedQuote?.vehicle_class === quote.vehicle_class;
            const cur = quote.display_currency ?? quote.currency;
            const amount = quote.display_amount ?? quote.fare_total;
            return (
              <Pressable
                key={quote.vehicle_class}
                onPress={() => {
                  setSelectedQuote(quote);
                  setPaymentMethods([]);
                  setPaymentMethod("");
                  setPaymentError(null);
                  setIdempotencyKey(newIdempotencyKey());
                }}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                style={[styles.vehicleCard, selected ? styles.vehicleSelected : null]}
              >
                <View style={styles.vehicleHeader}>
                  <View style={styles.vehicleIcon}><Text style={styles.vehicleIconText}>🚘</Text></View>
                  <View style={styles.vehicleCopy}>
                    <Text style={styles.vehicleName}>{quote.display_name}</Text>
                    <Text style={styles.helperText}>{quote.vehicle_class.replace(/_/g, " ")}</Text>
                  </View>
                  <Text style={styles.vehiclePrice}>{formatMoney(Number(amount), cur)}</Text>
                </View>
                <Text style={styles.vehicleSub}>
                  {quote.display_is_approximate
                    ? "Indicative home-currency display · fare is " + formatMoney(quote.fare_total, quote.currency)
                    : "Authoritative fare · " + quote.currency}
                </Text>
                {selected ? <Text style={styles.selectedTag}>Selected</Text> : null}
              </Pressable>
            );
          })}
          {!loadingQuotes && !quoteError && quotes.length === 0 ? (
            <Text style={styles.helperText}>No fare options are available yet for this route.</Text>
          ) : null}
          <Text style={styles.helperText}>These are signed server quotes, not driver availability or a reservation. You will review and accept the fare before any driver is contacted.</Text>
          <ActionButton
            label="Review Booking"
            disabled={!selectedQuote || loadingQuotes}
            onPress={() => void continueToConfirm()}
          />
          <Pressable onPress={() => setStage("where")} style={styles.secondaryButton}>
            <Text style={styles.secondaryButtonText}>Edit trip details</Text>
          </Pressable>
        </Panel>
      ) : null}

      {stage === "confirm" ? (
        <Panel>
          <SectionTitle>Confirm your ride</SectionTitle>
          <StatusPill>{schedule === "later" ? "Pickup scheduled" : "Leaving now"}</StatusPill>
          <Text style={styles.helperText}>{fmtSchedule}</Text>
          <View style={styles.summary}>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>Pickup</Text>
              <Text style={styles.summaryValue}>{pickup?.label ?? "—"}</Text>
            </View>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>Destination</Text>
              <Text style={styles.summaryValue}>{dropoff?.label ?? "—"}</Text>
            </View>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>Service</Text>
              <Text style={styles.summaryValue}>{vip ? "VIP Service" : serviceType === "airport_departure" ? "Airport Transfer" : "Quick Ride"}</Text>
            </View>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>Ride</Text>
              <Text style={styles.summaryValue}>{selectedQuote?.display_name ?? "—"}</Text>
            </View>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>Fare display</Text>
              <Text style={styles.summaryValue}>{formatMoney(Number(displayAmount), displayCurrency)}{displayApprox ? " (approx.)" : ""}</Text>
            </View>
            {displayApprox ? (
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Authoritative fare</Text>
                <Text style={styles.summaryValue}>{formatMoney(selectedQuote?.fare_total ?? 0, selectedQuote?.currency ?? "USD")}</Text>
              </View>
            ) : null}
          </View>

          {breakdown ? (
            <View style={styles.fareBreakdown}>
              <Text style={styles.label}>Fare breakdown</Text>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Base fare</Text>
                <Text style={styles.summaryValue}>{displayBreakdown(breakdown.base_fare)}</Text>
              </View>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Distance {distanceKm != null ? "(" + distanceKm.toFixed(1) + " km)" : ""}</Text>
                <Text style={styles.summaryValue}>{displayBreakdown(breakdown.distance_charge)}</Text>
              </View>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Class multiplier</Text>
                <Text style={styles.summaryValue}>× {Number(breakdown.class_multiplier ?? 1).toFixed(2)}</Text>
              </View>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Surge multiplier</Text>
                <Text style={styles.summaryValue}>× {Number(breakdown.surge_multiplier ?? 1).toFixed(2)}</Text>
              </View>
              <View style={[styles.summaryRow, styles.totalRow]}>
                <Text style={styles.totalLabel}>Wallet invoice fare</Text>
                <Text style={styles.totalValue}>{formatMoney(selectedQuote?.fare_total ?? 0, selectedQuote?.currency ?? "USD")}</Text>
              </View>
            </View>
          ) : (
            <View style={styles.summary}>
              <Text style={styles.totalLabel}>Wallet invoice fare</Text>
              <Text style={styles.totalValue}>{formatMoney(selectedQuote?.fare_total ?? 0, selectedQuote?.currency ?? "USD")}</Text>
            </View>
          )}

          <Text style={styles.label}>How would you like to pay?</Text>
          {loadingPayments ? <ActivityIndicator color={BRAND} /> : null}
          {paymentError ? <Text style={styles.errorText}>{paymentError}</Text> : null}
          {paymentMethods.map(method => {
            const ready = method.status === "ready";
            const selected = paymentMethod === method.code;
            return (
              <Pressable
                key={method.code}
                accessibilityRole="radio"
                accessibilityState={{ checked: selected, disabled: !ready }}
                disabled={!ready}
                onPress={() => setPaymentMethod(method.code)}
                style={[
                  styles.paymentChoice,
                  selected ? styles.paymentSelected : null,
                  !ready ? styles.disabled : null
                ]}
              >
                <View style={[styles.radio, selected ? styles.radioSelected : null]} />
                <View style={styles.paymentCopy}>
                  <Text style={styles.paymentName}>{method.label}</Text>
                  <Text style={styles.helperText}>
                    {ready ? "Ready for this fare" : method.status_message ?? method.status.replace(/_/g, " ")}
                  </Text>
                </View>
              </Pressable>
            );
          })}
          {!loadingPayments && paymentMethods.length === 0 && !paymentError ? (
            <Text style={styles.helperText}>No payment methods were returned for this fare.</Text>
          ) : null}
          <Text style={styles.helperText}>No driver search has started yet. Confirming accepts the signed fare. You are not charged at this step; payment follows the selected Wallet method and Transport's payment rules.</Text>
          <ActionButton
            label="Confirm Fare & Request Ride"
            disabled={!paymentMethod || loadingPayments || submitting}
            onPress={() => void requestRide()}
          />
          <Pressable onPress={() => setStage("choose")} style={styles.secondaryButton}>
            <Text style={styles.secondaryButtonText}>Edit vehicle choice</Text>
          </Pressable>
          <Pressable onPress={() => setStage("where")} style={styles.secondaryButton}>
            <Text style={styles.secondaryButtonText}>Edit trip details</Text>
          </Pressable>
        </Panel>
      ) : null}

      {stage === "match" ? (
        <Panel>
          <View style={styles.matchingPanel}>
            <ActivityIndicator color={BRAND} size="large" />
            <SectionTitle>{requestError ? "Ride request not completed" : "Sending your ride request…"}</SectionTitle>
            <Text style={styles.helperText}>
              {requestError
                ? "AFCON360 could not confirm the request. No successful booking reference was returned. Review the message before retrying."
                : "Please wait while AFCON360 validates your signed fare and payment choice, saves your request and starts the driver search."}
            </Text>
          </View>
          <View style={styles.summary}>
            <Text style={styles.summaryLabel}>Pickup</Text>
            <Text style={styles.summaryValue}>{pickup?.label ?? "—"}</Text>
            <Text style={styles.summaryLabel}>Destination</Text>
            <Text style={styles.summaryValue}>{dropoff?.label ?? "—"}</Text>
            <Text style={styles.summaryLabel}>Ride</Text>
            <Text style={styles.summaryValue}>{selectedQuote?.display_name ?? "—"}</Text>
          </View>
          {requestError ? (
            <>
              <Text style={styles.errorText}>{requestError}</Text>
              <ActionButton
                label={submitting ? "Retrying…" : "Retry ride request"}
                disabled={submitting}
                onPress={() => void requestRide()}
              />
              <Pressable onPress={() => setStage("confirm")} style={styles.secondaryButton}>
                <Text style={styles.secondaryButtonText}>Back to confirmation</Text>
              </Pressable>
            </>
          ) : null}
        </Panel>
      ) : null}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  fieldGroup: { gap: 7, marginBottom: 13 },
  fieldLabel: { color: INK, fontSize: 13, fontWeight: "800" },
  input: {
    minHeight: 50, borderWidth: 1.5, borderColor: LINE, borderRadius: 13,
    paddingHorizontal: 13, color: INK, backgroundColor: "#FFFFFF", fontSize: 14
  },
  helperText: { color: MUTED, fontSize: 12, lineHeight: 18 },
  errorText: { color: RED, fontSize: 12, lineHeight: 18 },
  attribution: { color: MUTED, fontSize: 10, lineHeight: 15 },
  label: { color: INK, fontSize: 13, fontWeight: "800", marginTop: 9, marginBottom: 8 },
  routeRow: { flexDirection: "row", alignItems: "center", gap: 9 },
  routeFields: { flex: 1, minWidth: 0 },
  locationButton: {
    alignSelf: "flex-start", borderWidth: 1, borderColor: "#B8D9C9",
    backgroundColor: BRAND_SOFT, borderRadius: 999, paddingHorizontal: 13,
    paddingVertical: 9, marginBottom: 15
  },
  locationButtonText: { color: BRAND_DARK, fontSize: 12, fontWeight: "800" },
  sourceText: { color: BRAND_DARK, fontSize: 11, marginTop: -8, marginBottom: 10 },
  swapButton: {
    width: 42, height: 42, borderRadius: 22, borderWidth: 1,
    borderColor: LINE, alignItems: "center", justifyContent: "center",
    backgroundColor: "#FFFFFF", marginBottom: 26
  },
  swapText: { fontSize: 22, color: BRAND_DARK, fontWeight: "700" },
  searchStatus: { flexDirection: "row", alignItems: "center", gap: 9, paddingVertical: 5 },
  searchResults: { gap: 7, marginTop: 2 },
  searchResult: {
    backgroundColor: BRAND_SOFT, borderWidth: 1, borderColor: "#D4E8DC",
    padding: 12, borderRadius: 11, gap: 3, minHeight: 52, justifyContent: "center"
  },
  searchResultTitle: { color: INK, fontSize: 13, fontWeight: "700" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginBottom: 10 },
  chip: { borderWidth: 1, borderColor: LINE, backgroundColor: "#FFFFFF", paddingHorizontal: 12, paddingVertical: 9, borderRadius: 99 },
  chipText: { color: INK, fontSize: 11, fontWeight: "700" },
  serviceRow: { flexDirection: "row", gap: 7, marginBottom: 12 },
  serviceChoice: {
    flex: 1, minHeight: 59, borderWidth: 1.5, borderColor: LINE,
    borderRadius: 12, padding: 7, alignItems: "center", justifyContent: "center",
    backgroundColor: "#FFFFFF"
  },
  serviceSelected: { borderColor: "#15803D", backgroundColor: "#F0FDF4" },
  serviceAirportSelected: { borderColor: "#2563EB", backgroundColor: "#EFF6FF" },
  serviceVipSelected: { borderColor: "#CA8A04", backgroundColor: "#FEFCE8" },
  serviceIcon: { color: BRAND_DARK, fontSize: 16, fontWeight: "900" },
  serviceName: { color: INK, fontSize: 10, fontWeight: "800", textAlign: "center" },
  scheduleRow: { flexDirection: "row", gap: 8, marginBottom: 9 },
  scheduleChoice: { flex: 1, borderRadius: 99, backgroundColor: "#F0F3F1", padding: 11, alignItems: "center" },
  scheduleSelected: { backgroundColor: BRAND_SOFT, borderWidth: 1, borderColor: "#9BC8B5" },
  scheduleText: { color: INK, fontSize: 12, fontWeight: "800" },
  mapFrame: { height: 285, borderRadius: 16, overflow: "hidden", backgroundColor: "#E9F0EB", marginTop: 7 },
  map: { flex: 1, backgroundColor: "#E9F0EB" },
  mapOverlay: {
    position: "absolute", left: 0, right: 0, top: 80, alignItems: "center",
    justifyContent: "center", gap: 8, pointerEvents: "none"
  },
  selectedRoute: { borderTopWidth: 1, borderTopColor: LINE, marginTop: 9, paddingTop: 9, gap: 5 },
  selectedRouteText: { color: INK, fontSize: 11, lineHeight: 16 },
  progress: { flexDirection: "row", alignItems: "center", paddingHorizontal: 3, paddingVertical: 12, marginBottom: 6 },
  progressStep: { alignItems: "center", gap: 4 },
  progressNumber: { width: 25, height: 25, borderRadius: 13, backgroundColor: LINE, alignItems: "center", justifyContent: "center" },
  progressDone: { backgroundColor: BRAND_SOFT },
  progressActive: { backgroundColor: BRAND },
  progressNumberText: { color: MUTED, fontSize: 11, fontWeight: "900" },
  progressNumberTextActive: { color: BRAND_DARK },
  progressLabel: { color: MUTED, fontSize: 10, fontWeight: "700" },
  progressLabelActive: { color: BRAND_DARK },
  progressLine: { height: 2, flex: 1, backgroundColor: LINE, marginHorizontal: 6, marginBottom: 14 },
  progressLineDone: { backgroundColor: BRAND },
  vehicleCard: { borderWidth: 1.5, borderColor: LINE, borderRadius: 15, padding: 13, marginTop: 10, backgroundColor: "#FFFFFF", gap: 8 },
  vehicleSelected: { borderColor: BRAND, backgroundColor: "#F0FBF2" },
  vehicleHeader: { flexDirection: "row", alignItems: "center", gap: 10 },
  vehicleIcon: { width: 43, height: 43, borderRadius: 12, backgroundColor: BRAND_SOFT, alignItems: "center", justifyContent: "center" },
  vehicleIconText: { fontSize: 20 },
  vehicleCopy: { flex: 1, gap: 3 },
  vehicleName: { color: INK, fontSize: 14, fontWeight: "900" },
  vehiclePrice: { color: "#178A3E", fontSize: 14, fontWeight: "900", textAlign: "right" },
  vehicleSub: { color: MUTED, fontSize: 11, lineHeight: 16 },
  selectedTag: { color: BRAND_DARK, fontSize: 11, fontWeight: "900" },
  summary: { backgroundColor: "#F5F7F5", borderRadius: 13, padding: 13, gap: 7, marginTop: 10, marginBottom: 12 },
  summaryRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 12, paddingVertical: 3 },
  summaryLabel: { color: MUTED, fontSize: 11, flex: 1 },
  summaryValue: { color: INK, fontSize: 12, fontWeight: "700", flex: 1.5, textAlign: "right" },
  fareBreakdown: { borderWidth: 1, borderColor: LINE, borderRadius: 13, padding: 13, gap: 7, marginBottom: 12 },
  totalRow: { borderTopWidth: 1, borderTopColor: LINE, marginTop: 5, paddingTop: 10 },
  totalLabel: { color: INK, fontSize: 12, fontWeight: "900" },
  totalValue: { color: BRAND_DARK, fontSize: 17, fontWeight: "900", marginTop: 4 },
  paymentChoice: {
    flexDirection: "row", alignItems: "center", gap: 11, borderWidth: 1,
    borderColor: LINE, borderRadius: 12, padding: 12, marginTop: 8,
    backgroundColor: "#FFFFFF"
  },
  paymentSelected: { borderColor: BRAND, backgroundColor: BRAND_SOFT },
  paymentCopy: { flex: 1, gap: 3 },
  paymentName: { color: INK, fontSize: 13, fontWeight: "800" },
  radio: { width: 19, height: 19, borderRadius: 10, borderWidth: 1.5, borderColor: MUTED },
  radioSelected: { borderWidth: 6, borderColor: BRAND },
  disabled: { opacity: 0.55 },
  secondaryButton: { alignItems: "center", paddingVertical: 13 },
  secondaryButtonText: { color: BRAND_DARK, fontSize: 13, fontWeight: "800" },
  matchingPanel: { alignItems: "center", gap: 10, paddingVertical: 16 },
});
