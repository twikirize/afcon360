# Fix 2.4 — Record

Status: PASS
Date: 2026-09-23
Owner: [name]

Files changed (Fix 2.4's own contribution only):
- app/config.py (+13) — TILE_PROVIDER_URL_TEMPLATE, TILE_PROVIDER_ATTRIBUTION via os.getenv with OSM defaults
- app/transport/routes.py — current_app import + tile_url/tile_attribution in home() and new_home() ctx dicts (3 lines total)
- templates/transport/home.html (-2/+2) — tileUrl + attribution from config
- templates/transport/new_home.html (-2/+2) — same
- tests/transport/test_tile_provider_config.py (new) — 3 tests

Evidence: docs/transport/fixes/Fix-2.4-evidence.md

Behavior: Rider map tile source and attribution are now supplied by
application config (env-driven). Default preserves OSM behavior. An
operator sets TILE_PROVIDER_URL_TEMPLATE and TILE_PROVIDER_ATTRIBUTION
in the environment to switch providers — no code change required.
Both rider templates (home.html, new_home.html) consume the same
config contract in lockstep.

Template lockstep: home.html and new_home.html changed identically.
Any pre-existing formatting difference (spacing in center, IIFE line
wrapping) is preserved, not harmonized.

Residual risk:
- Attribution uses `|safe` because providers commonly return HTML
  <a> tags. The value comes from server config, not user input. A
  future node should validate operator-supplied attribution at
  config-load time to reject unexpected markup.
- Tile URL is inserted into a single-quoted JS string. URLs with
  embedded single quotes would break. Acceptable because URLs never
  contain single quotes; documented in the contract.

Follow-ups:
- templates/transport/bookings/show.html:295 feeds GeoMap.init and
  still hardcodes the OSM attribution. Out of Fix 2.4 scope per
  Contract §4. Record as a follow-up node for the same treatment.
- templates/transport/drivers/location.html and
  vehicles/location.html use Leaflet directly and hardcode OSM. Out
  of scope. Follow-up.
- static/js/geo/geo-map.js has no hardcoded fallback URL — verified
  during Step 1 read. Not touched.

Gate reference: Edition 2.0, Part VII, Fix 2.4