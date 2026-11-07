# Driver recent-demand map overlay

**Status:** Implemented on `feat/driver-demand-heatmap-20261107` for review.

## Product contract

The canonical driver workspace remains `/transport/driver-dashboard`. The map uses the existing shared GEO/Leaflet renderer and its existing GPS publisher. This feature adds a read-only demand overlay to that map; it does not replace the dashboard or add another GPS watcher/publisher.

The overlay is a historical concentration view, not a live-demand promise:

- Source: submitted Transport booking requests in the preceding 24 hours, excluding drafts and cancelled requests through the existing `booking_request_points()` service.
- Display: fixed GEO grid cells (~1.1 km at the equator); only cells with at least 3 requests are returned.
- Scope: cells within 25 km straight-line distance of the driver's last published position.
- Location gate: a valid last-published driver position no older than GEO's 300-second location freshness limit is required. A default map centre or one-time local device-centering action is not accepted as the server-side location gate.
- Data minimization: response contains cell centres and aggregate request counts only. No booking references, customer locations as individual points, driver identifiers, fares, supply counts, surge values, or dispatch recommendations.
- The response includes its UTC time window and computation timestamp; UI labels it "last 24 hours", never "live".
- Empty, stale-location, and unavailable states remain explicit. Demand map failure does not disable the driver's workspace, location publishing, or trip actions.

## Security and operations

The endpoint is authenticated, requires explicit Driver context, and is covered by the Transport module gate. It is read-only and returns `Cache-Control: private, no-store` and `Vary: Cookie`. It makes no schema or migration changes and performs no Wallet, Booking, driver-status, or dispatch writes.

## Verification

The accompanying regression covers:
- a fresh driver position and 3 requests aggregating to one nearby cell;
- no individual booking, driver, or fare data in the response;
- private/no-store response headers;
- stale driver-location suppression; and
- rejection when Driver context is not explicitly active.

The browser contract continues to enforce one GPS publisher: `driver-dashboard.js` owns location publishing; the map adapter performs only the read-only demand GET and local map rendering.
