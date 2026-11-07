"""Cross-layer browser contract guards for the transport rider/driver UI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_driver_offer_poller_consumes_standard_api_envelope():
    poller = _read("static/js/modules/transport/offer-poller.js")
    callback = _read("static/js/modules/transport/driver_offer_poll.js")
    assert "res.data && Array.isArray(res.data.offers)" in poller
    assert "res.offers || []" not in poller
    assert "res && res.data && res.data.offers" in callback


def test_driver_offer_refresh_baseline_advances_after_snapshot():
    callback = _read("static/js/modules/transport/driver_offer_poll.js")
    assert "baseline = nextKey;" in callback
    assert "baselineRefs = refsList(nextKey);" in callback


def test_post_confirmation_matching_does_not_infer_live_supply_from_quotes():
    matching = _read("static/js/modules/transport/rider_matching.js")
    template = _read("templates/transport/rides/show.html")
    assert "ride-options" not in matching
    assert "available_count" not in matching
    assert "No vehicles available nearby" not in matching
    assert "data-options-url" not in template
    assert "Driver and vehicle details appear after acceptance." in template
    assert "A driver and vehicle are confirmed only after a driver accepts." in template
    assert "var DRIVER_ACCEPTED =" in matching
    assert "if (DRIVER_ACCEPTED[st])" in matching
    assert "optionsUrl" not in matching


def test_wallet_commitment_requires_ready_status():
    service = _read("app/transport/services/ride_request_service.py")
    assert 'if str(method.get("status") or "").strip().lower() == "ready"' in service


def test_geo_tracking_has_owner_scoped_http_fallback():
    route = _read("app/geo/routes.py")
    client = _read("static/js/geo/geo-realtime.js")
    template = _read("templates/transport/rides/show.html")
    assert '@geo_bp.get("/api/booking/<booking_reference>/location")' in route
    assert "TrackingService.get_rider_tracking_subject(" in route
    assert "build_location_event(" in route
    assert "pollUrl: '/geo/api/booking/'" in template
    assert "function startPolling()" in client
    assert "sse-retry-budget-exhausted" in client
    assert "terminalState = error.terminalState || 'unavailable'" in client
    assert "auth-required" in client
    assert "access-denied" in client
    assert "Session expired — sign in again" in template
    assert "Location access denied" in template
    assert "Live tracking unavailable" in template
    assert 'response.headers["Cache-Control"] = "private, no-store, max-age=0"' in route
    assert 'response.headers["Vary"] = "Cookie"' in route


def test_request_first_tracker_polls_single_flight_and_stops_cleanly():
    template = _read("templates/transport/rides/request_show.html")
    assert "var inFlight = false;" in template
    assert "REQUEST_TIMEOUT_MS = 10000" in template
    assert "signal: controller ? controller.signal : undefined" in template
    assert "document.addEventListener('visibilitychange'" in template
    assert "window.setInterval(poll, 4000)" not in template
    assert "if (!stopped && !document.hidden) schedulePoll(nextDelay);" in template


def test_cancellation_copy_never_claims_a_refund_was_processed():
    template = _read("templates/transport/rides/show.html")
    assert "Calculated potential refund:" in template
    assert "No refund was processed; any eligible refund requires separate Wallet processing." in template
    assert "Refund due:" not in template


def test_rider_progress_includes_no_show_and_dispute_states():
    sync = _read("static/js/modules/transport/rider_status_sync.js")
    assert "'no_show'" in sync
    assert "'disputed'" in sync
    assert "No-show" in sync
    assert "Disputed — under review" in sync

def test_driver_dashboard_map_uses_shared_geo_renderer_without_duplicate_publisher():
    template = _read("templates/transport/driver/driver_dashboard.html")
    route = _read("app/transport/routes.py")
    adapter = _read("static/js/modules/transport/driver-dashboard-map.js")
    assert "build_public_map_config(load_geo_config(current_app))" in route
    assert "map_config=map_config" in route
    assert 'id="driverMap"' in template
    assert 'data-geo-map-status="pending"' in template
    assert "cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css" in template
    assert "cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js" in template
    assert "js/geo/geo-map.js" in template
    assert "driver-dashboard-map.js" in template
    assert "maplibre" not in template.lower()
    assert "window.GeoMap.init" in adapter
    assert "navigator.geolocation.getCurrentPosition" in adapter
    # This adapter may fetch only the read-only, driver-scoped demand
    # snapshot. It never publishes location or starts a second GPS watch.
    # driver-dashboard.js remains the sole owner of server publishing.
    assert "container.dataset.demandUrl" in adapter
    assert "method: 'GET'" in adapter
    assert "credentials: 'same-origin'" in adapter
    assert "XMLHttpRequest" not in adapter
    assert "navigator.geolocation.watchPosition" not in adapter
    assert "driver_demand_cells" in template
    assert 'id="driverDemandRefreshBtn"' in template
    assert "last 24 hours" in adapter


def test_csrf_refresh_does_not_rotate_session_seed():
    app_init = _read("app/__init__.py")
    start = app_init.index("def issue_csrf_token():")
    end = app_init.index("@app.errorhandler(CSRFError)", start)
    refresh = app_init[start:end]
    assert "generate_csrf()" in refresh
    assert "session.pop('csrf_token'" not in refresh
    assert 'Cache-Control"] = "private, no-store, max-age=0"' in refresh
    assert 'Vary"] = "Cookie"' in refresh

