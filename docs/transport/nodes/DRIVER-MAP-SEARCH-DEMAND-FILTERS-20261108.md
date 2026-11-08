# Driver map place search and demand filters

**Node ID:** DRIVER-MAP-SEARCH-DEMAND-FILTERS-20261108
**Branch:** feat/driver-map-search-demand-filters-20261108
**Scope:** Existing website driver workspace map only

## Changes

- Adds place search to the canonical driver map using the existing GEO `/geo/api/geocode` endpoint.
- Keeps provider attribution visible whenever geocoding results are shown.
- Uses DOM text nodes for provider-supplied place labels; labels are not injected as HTML.
- Adds high / medium / low filters to the real demand overlay:
  - High: 10 or more requests in a cell.
  - Medium: 6–9 requests in a cell.
  - Low: 3–5 requests in a cell.
- Filters only the existing aggregate response. It does not add a new data source, reveal request-level locations, change the API contract, or influence dispatch.
- Retains the shared GEO map renderer and leaves `driver-dashboard.js` as the sole GPS acquisition and publishing owner.

## Deliberately excluded

The prototype's traffic switch had no traffic provider or implementation and remains excluded.

The prototype's hard-coded Kampala hotspots, sample trip list, sample earnings graph, and simulated daily earnings targets remain excluded. Earnings analytics must use currency-separated, authoritative captured-payment data and the driver's presentation currency. Daily goals also need a defined driver-local calendar day and server-persisted preference before they can be presented as reliable progress.

## Verification

- Frontend contract tests cover GEO search URL, result attribution, text-safe rendering, and demand threshold mapping.
- Driver-console route test asserts the controls are included in the authenticated canonical driver workspace.
- CI must run the focused PostgreSQL transport regression workflow and the repository's other required PR checks before merge.
