import { getSelectedApiBaseUrl } from "./api";

// The app must never call OpenStreetMap (or any tile CDN) directly: the
// request carries the app's own User-Agent, which OSM answers with
// "418 Access blocked". Tiles come from our server, which identifies itself
// and caches them (/geo/api/tiles/<z>/<x>/<y>.png).
const TILE_PATH = "/geo/api/tiles/{z}/{x}/{y}.png";

let cachedOrigin: string | null = null;
let inFlight: Promise<string> | null = null;

function trimOrigin(origin: string): string {
  return origin.replace(/\/+$/, "");
}

/** Absolute tile template for the currently selected server. */
export function tileUrlTemplateFor(origin: string): string {
  return trimOrigin(origin) + TILE_PATH;
}

/**
 * Origin of the server the rider is signed in to (public or preview).
 * Read once and reused: the map WebView resolves the tile template
 * relatively against this origin.
 */
export async function getMapOrigin(): Promise<string> {
  if (cachedOrigin) return cachedOrigin;
  if (!inFlight) {
    inFlight = getSelectedApiBaseUrl()
      .then(origin => {
        cachedOrigin = trimOrigin(origin);
        return cachedOrigin;
      })
      .finally(() => {
        inFlight = null;
      });
  }
  return inFlight;
}

/** Called when the preview server changes so the map re-resolves its tiles. */
export function clearMapOriginCache(): void {
  cachedOrigin = null;
  inFlight = null;
}

export const MAP_TILE_PATH = TILE_PATH;
