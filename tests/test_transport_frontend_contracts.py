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
    assert "data['driver_id']" not in route


def test_rider_progress_includes_no_show_and_dispute_states():
    sync = _read("static/js/modules/transport/rider_status_sync.js")
    assert "'no_show'" in sync
    assert "'disputed'" in sync
    assert "No-show" in sync
    assert "Disputed — under review" in sync
