export type LocationSource = "search" | "gps" | "map";

export type GeocodeCandidate = {
  label: string;
  latitude: number;
  longitude: number;
  provider: string;
  osm_type?: string;
  osm_id?: string | number;
};

export type Place = GeocodeCandidate & {
  source: LocationSource;
  geocode?: GeocodeCandidate;
};

export type PlaceSearchStatus = "idle" | "loading" | "success" | "error";

export type PlaceSearchState = {
  query: string;
  status: PlaceSearchStatus;
  results: GeocodeCandidate[];
  attribution: string | null;
  error: string | null;
};

export type PlaceSearchCacheEntry = {
  expiresAt: number;
  results: GeocodeCandidate[];
  attribution: string | null;
};

export const PLACE_SEARCH_CACHE_POSITIVE_TTL_MS = 24 * 60 * 60 * 1000;
export const PLACE_SEARCH_CACHE_NEGATIVE_TTL_MS = 5 * 60 * 1000;
export const PLACE_SEARCH_CACHE_MAX_ENTRIES = 80;

export type Quote = {
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

export type PaymentMethod = {
  code: string;
  label: string;
  status: string;
  status_message?: string;
  is_default?: boolean;
};

export type MapMessage =
  | { type: "map_ready" }
  | { type: "map_tap" | "map_drag"; latitude: number; longitude: number; side?: "pickup" | "dropoff" };

export type ReverseResponse = {
  success?: boolean;
  presentable?: boolean;
  display_name?: string | null;
  provider?: string;
  attribution?: string | null;
};

export type Stage = "where" | "choose" | "confirm" | "match";

export type RideServiceType = "on_demand" | "airport_departure";
export type RideVip = boolean;
export type RideSchedule = "now" | "later";

export type RideBookingRequest = {
  idempotency_key: string;
  pickup: {
    latitude: number;
    longitude: number;
    address: string;
    provider: string;
    osm_type?: string;
    osm_id?: string | number;
  };
  dropoff: {
    latitude: number;
    longitude: number;
    address: string;
    provider: string;
    osm_type?: string;
    osm_id?: string | number;
  };
  pickup_source: LocationSource;
  dropoff_source: LocationSource;
  pickup_geocode?: GeocodeCandidate;
  dropoff_geocode?: GeocodeCandidate;
  service_type: RideServiceType;
  vehicle_class: string;
  passenger_count: number;
  booking_mode: "scheduled" | "instant";
  pickup_time?: string;
  payment_method: string;
  currency: string;
  fare_quote_token: string;
  confirmed_fare_amount: string;
};