import type { Place, GeocodeCandidate, PlaceSearchState, PlaceSearchCacheEntry } from "./types";

const placeSearchCache = new Map<string, PlaceSearchCacheEntry>();

export function normalizePlaceSearchQuery(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

export function readPlaceSearchCache(key: string): PlaceSearchCacheEntry | null {
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

export function writePlaceSearchCache(
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

export const EMPTY_PLACE_SEARCH_STATE: PlaceSearchState = {
  query: "",
  status: "idle",
  results: [],
  attribution: null,
  error: null
};

export function validGeocodeCandidate(value: unknown): value is GeocodeCandidate {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<GeocodeCandidate>;
  return typeof candidate.label === "string" && candidate.label.trim().length > 0 &&
    typeof candidate.provider === "string" && candidate.provider.trim().length > 0 &&
    typeof candidate.latitude === "number" && Number.isFinite(candidate.latitude) &&
    candidate.latitude >= -90 && candidate.latitude <= 90 &&
    typeof candidate.longitude === "number" && Number.isFinite(candidate.longitude) &&
    candidate.longitude >= -180 && candidate.longitude <= 180;
}

export function validCoordinate(place: Pick<Place, "latitude" | "longitude">): boolean {
  return Number.isFinite(place.latitude) &&
    Number.isFinite(place.longitude) &&
    place.latitude >= -90 && place.latitude <= 90 &&
    place.longitude >= -180 && place.longitude <= 180;
}

export function distanceSquared(a: Place, latitude: number, longitude: number): number {
  const latScale = Math.cos(latitude * Math.PI / 180);
  const x = (a.longitude - longitude) * latScale;
  const y = a.latitude - latitude;
  return x * x + y * y;
}

export function formatMoney(amount: number, currency: string): string {
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

export function friendlyError(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message;
  return fallback;
}

export function validLocalSchedule(value: string): boolean {
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

export function newIdempotencyKey(): string {
  return "mobile-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
}