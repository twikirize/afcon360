"""UI-01 — GEO forward-geocode search endpoint + booking evidence seam.

Proves the shared UI-01 contract (AGENT 1 scope):

  * ``GET /geo/api/geocode?q=<query>&limit=<n>`` — DISCOVERY boundary:
    anonymous-or-authenticated (no login required, no owner-only
    ``geo.view`` permission, no GEO module hard-gate) — returns 200 with
    normalized results fetched through a controlled localhost fake
    Photon (real HTTP round-trip through OUR adapter; no external
    traffic, never live Photon);
  * every provider miss — disabled, unconfigured, network failure,
    timeout, HTTP error, malformed response, empty collection —
    degrades to ``results == []`` with ``success == true`` (and
    ``provider == "unresolved"`` when nothing is wired): never
    fabricated coordinates, never a wholesale ``raw`` dump;
  * blank/whitespace/missing ``q`` -> 400 INVALID_QUERY; bad ``limit``
    -> 400 INVALID_LIMIT; ``limit`` is clamped to max 5;
  * malformed provider features are skipped (not fabricated) and the
    OSM provenance pair is emitted only when the provider supplied it;
  * ``geocode_result_from_candidate`` rebuilds ONLY truthful evidence
    (resolved + real provider + numeric/finite/in-range coordinates +
    OSM datum pair kept verbatim) and refuses non-mappings, missing /
    empty / "unresolved" providers and bad coordinates;
  * booking seam: ``pickup_source="search"`` WITHOUT ``pickup_geocode``
    provider evidence raises ValidationError (field ``pickup_source``)
    and creates NO row; WITH the echoed candidate the persisted
    snapshot carries ``source == "search"``,
    ``resolution_method == "forward_geocode"``, the submitted
    coordinates and ``provenance.authority == "photon"``; the gps/map
    paths without evidence keep working (regression).
"""

import json
import socket
import threading
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests

URL = "/geo/api/geocode"

_PICKUP = (0.3136, 32.5811)
_DROPOFF = (0.3476, 32.5825)


# ---------------------------------------------------------------------------
# Localhost fake Photon (pattern from tests/test_geo_geocoding.py)
# ---------------------------------------------------------------------------

def _feature(lon, lat, name, city="Kampala", country="Uganda",
             osm_id=12345, osm_type="N"):
    properties = {"name": name, "city": city, "country": country}
    if osm_id is not None:
        properties["osm_id"] = osm_id
    if osm_type is not None:
        properties["osm_type"] = osm_type
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties,
    }


FAKE_COLLECTION = {
    "type": "FeatureCollection",
    "features": [
        # GeoJSON [lon, lat] order — adapter must convert lat-first.
        _feature(32.5825, 0.3476, "Nakasero Market"),
        _feature(32.5800, 0.3500, "Nakasero Hill"),
    ],
}


class _FakePhotonHandler(BaseHTTPRequestHandler):
    """Controlled stand-in. Records requests for param assertions."""
    calls = []
    mode = "ok"  # ok | empty | error | malformed

    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        type(self).calls.append((parsed.path, parse_qs(parsed.query)))
        if self.mode == "error":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")
        elif self.mode == "malformed":
            payload = json.dumps({"nope": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.mode == "empty":
            payload = json.dumps(
                {"type": "FeatureCollection", "features": []}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            payload = json.dumps(FAKE_COLLECTION).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)


@pytest.fixture(scope="module")
def fake_photon():
    _FakePhotonHandler.calls = []
    _FakePhotonHandler.mode = "ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakePhotonHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield (f"http://127.0.0.1:{server.server_port}", _FakePhotonHandler)
    server.shutdown()
    thread.join(timeout=5)


class _PayloadHandler(BaseHTTPRequestHandler):
    """Serves whatever collection the test assigns to `payload`."""
    payload = {}

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps(type(self).payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def custom_collection_server():
    """Second localhost fake for payloads the shared modes don't cover."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PayloadHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield (f"http://127.0.0.1:{server.server_port}", _PayloadHandler)
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture()
def photon_env(monkeypatch, fake_photon):
    """Point the endpoint's env-config at the fake Photon (enabled).

    Neutralizes Geoapify so the fake Photon is the ONLY wired provider:
    the repo .env now carries a real GEOAPIFY keypair, which would
    otherwise make Geoapify primary answer first and these Photon-contract
    tests non-hermetic."""
    base_url, handler = fake_photon
    handler.calls = []
    handler.mode = "ok"
    monkeypatch.setenv("GEO_PHOTON_URL", base_url)
    monkeypatch.setenv("GEO_PHOTON_ENABLED", "true")
    monkeypatch.setenv("GEOAPIFY_ENABLED", "false")
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)
    return base_url, handler


# ---------------------------------------------------------------------------
# Guards: discovery boundary — anonymous search allowed, no owner-only
# permission, no module hard-gate
# ---------------------------------------------------------------------------

def test_endpoint_allows_anonymous_search(anonymous_client, photon_env):
    """Discovery boundary (authorized): an anonymous rider gets 200 with
    the same candidate contract — no login, no redirect. This replaces
    the old login-only contract test."""
    resp = anonymous_client.get(URL, query_string={"q": "Nakasero"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "photon"
    assert payload["results"]
    first = payload["results"][0]
    assert first["label"] == "Nakasero Market, Kampala, Uganda"
    assert first["provider"] == "photon"


def test_anonymous_rate_limit_and_min_length(anonymous_client):
    """Abuse controls hold without authentication: single character is
    an honest no-result with zero provider traffic."""
    resp = anonymous_client.get(URL, query_string={"q": "K"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "unresolved"
    assert payload["results"] == []


def test_standard_rider_without_geo_permission_can_search(
        authenticated_client, photon_env):
    """No require_permission('geo.view'): a plain rider gets 200."""
    resp = authenticated_client.get(URL, query_string={"q": "Nakasero"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "photon"
    assert payload["results"]


@contextmanager
def _preserved_module_flags(app):
    """Snapshot + restore persisted MODULE_FLAGS around a test."""
    from app.models.system_config import SystemConfig
    from app.utils.module_toggle_service import ModuleToggleService
    with app.app_context():
        row_present = (
            SystemConfig.query.filter_by(
                key=ModuleToggleService.SETTINGS_KEY).first()
            is not None
        )
        previous = ModuleToggleService._fetch_stored_flags()
    try:
        yield previous
    finally:
        with app.app_context():
            from app.extensions import db
            if row_present:
                SystemConfig.set(
                    ModuleToggleService.SETTINGS_KEY,
                    json.dumps(previous),
                    value_type='json',
                    description='Module flags',
                    commit=True,
                )
            else:
                row = SystemConfig.query.filter_by(
                    key=ModuleToggleService.SETTINGS_KEY
                ).first()
                if row is not None:
                    db.session.delete(row)
                    db.session.commit()
            ModuleToggleService.load_overrides_into_app()


def test_geo_module_disabled_does_not_block_search(
        app, authenticated_client, photon_env):
    """No require_module_enabled('geo'): a disabled GEO module degrades
    the provider truthfully instead of blocking the endpoint."""
    from app.utils.module_toggle_service import ModuleToggleService
    with _preserved_module_flags(app):
        with app.app_context():
            ModuleToggleService.set_flag('geo', False, updated_by=None)
        resp = authenticated_client.get(
            URL, query_string={"q": "Nakasero"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


# ---------------------------------------------------------------------------
# Valid search
# ---------------------------------------------------------------------------

def test_valid_search_returns_normalized_results(
        authenticated_client, photon_env):
    _, handler = photon_env
    resp = authenticated_client.get(URL, query_string={"q": "  Nakasero "})
    assert resp.status_code == 200
    payload = resp.get_json()

    assert payload["success"] is True
    assert payload["query"] == "Nakasero"  # echoed stripped
    assert payload["provider"] == "photon"
    assert len(payload["results"]) == 2

    for item in payload["results"]:
        assert set(item) <= {"label", "latitude", "longitude",
                             "provider", "osm_type", "osm_id"}
        assert isinstance(item["label"], str) and item["label"]
        assert item["provider"] == "photon"
        assert -90 <= item["latitude"] <= 90
        assert -180 <= item["longitude"] <= 180

    first = payload["results"][0]
    # GeoJSON [lon, lat] converted back to latitude-first order.
    assert first["latitude"] == pytest.approx(0.3476)
    assert first["longitude"] == pytest.approx(32.5825)
    assert first["label"] == "Nakasero Market, Kampala, Uganda"
    # OSM provenance datum pair comes from provider raw only.
    assert first["osm_type"] == "N"
    assert first["osm_id"] == 12345
    assert "raw" not in first

    # Default limit reaches the provider (5 when omitted).
    assert handler.calls, "endpoint must GET the provider"
    path, params = handler.calls[-1]
    assert path == "/api"
    assert params.get("q") == ["Nakasero"]
    assert params.get("limit") == ["5"]


def test_limit_is_clamped_to_max_five(authenticated_client, photon_env):
    _, handler = photon_env
    resp = authenticated_client.get(
        URL, query_string={"q": "Nakasero", "limit": "50"})
    assert resp.status_code == 200
    _, params = handler.calls[-1]
    assert params.get("limit") == ["5"]  # clamped, never 50


# ---------------------------------------------------------------------------
# Truthful degradation: every miss -> results == [], success == true
# ---------------------------------------------------------------------------

def test_empty_collection_returns_empty_results(
        authenticated_client, photon_env):
    _, handler = photon_env
    handler.mode = "empty"
    resp = authenticated_client.get(URL, query_string={"q": "Nowhere XYZ"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["results"] == []


def test_disabled_provider_returns_unresolved_without_network(
        authenticated_client, monkeypatch):
    """Unconfigured/disabled -> provider 'unresolved', empty results,
    and ZERO network traffic: a miss never fabricates coordinates."""
    monkeypatch.delenv("GEO_PHOTON_URL", raising=False)
    monkeypatch.delenv("GEO_PHOTON_ENABLED", raising=False)
    # Neutralize ambient Geoapify (repo .env carries a live keypair):
    # this test proves the no-provider path, so Geoapify must also be off.
    monkeypatch.setenv("GEOAPIFY_ENABLED", "false")
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)
    posted = []
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: posted.append((a, k)))

    resp = authenticated_client.get(URL, query_string={"q": "Nakasero"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "unresolved"
    assert payload["results"] == []
    assert posted == []  # no network touched


def test_network_failure_degrades_truthfully(authenticated_client,
                                             monkeypatch):
    """Connection refused (dead endpoint) -> 200, empty results."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    dead_port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setenv("GEO_PHOTON_URL", f"http://127.0.0.1:{dead_port}")
    monkeypatch.setenv("GEO_PHOTON_ENABLED", "true")
    # Neutralize ambient Geoapify (repo .env carries a live keypair) so
    # the dead-Photon path is what the endpoint actually exercises.
    monkeypatch.setenv("GEOAPIFY_ENABLED", "false")
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)

    resp = authenticated_client.get(URL, query_string={"q": "Nakasero"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["results"] == []


def test_timeout_degrades_truthfully(authenticated_client, photon_env,
                                     monkeypatch):
    def _timeout(*args, **kwargs):
        raise requests.Timeout("simulated provider timeout")

    monkeypatch.setattr(requests, "get", _timeout)
    resp = authenticated_client.get(URL, query_string={"q": "Nakasero"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["results"] == []


def test_http_error_degrades_truthfully(authenticated_client, photon_env):
    _, handler = photon_env
    handler.mode = "error"
    resp = authenticated_client.get(URL, query_string={"q": "Nakasero"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["results"] == []


def test_malformed_response_degrades_truthfully(
        authenticated_client, photon_env):
    _, handler = photon_env
    handler.mode = "malformed"
    resp = authenticated_client.get(URL, query_string={"q": "Nakasero"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["results"] == []


def test_malformed_feature_skipped_without_fabrication(
        authenticated_client, photon_env, custom_collection_server,
        monkeypatch):
    """A collection mixing one malformed feature with one valid feature
    (no OSM properties) yields exactly the valid hit — malformed
    entries are skipped, never fabricated, and absent OSM keys are
    omitted rather than invented."""
    base_url, handler = custom_collection_server
    handler.payload = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature"},  # no geometry/properties -> skipped
            {
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [32.5825, 0.3476]},
                "properties": {"name": "Nakasero Market",
                               "city": "Kampala",
                               "country": "Uganda"},  # no osm_* keys
            },
        ],
    }
    monkeypatch.setenv("GEO_PHOTON_URL", base_url)

    resp = authenticated_client.get(URL, query_string={"q": "Nakasero"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert len(payload["results"]) == 1
    item = payload["results"][0]
    assert item["latitude"] == pytest.approx(0.3476)
    assert item["longitude"] == pytest.approx(32.5825)
    assert "osm_type" not in item  # absent datum stays absent
    assert "osm_id" not in item


# ---------------------------------------------------------------------------
# Input validation: 400 codes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("q", [None, "", "   "])
def test_blank_or_missing_query_rejected(authenticated_client, q):
    qs = {} if q is None else {"q": q}
    resp = authenticated_client.get(URL, query_string=qs)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert payload["code"] == "INVALID_QUERY"
    assert payload["error"]


@pytest.mark.parametrize("limit", ["0", "-1", "abc", ""])
def test_invalid_limit_rejected(authenticated_client, limit):
    resp = authenticated_client.get(
        URL, query_string={"q": "Nakasero", "limit": limit})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert payload["code"] == "INVALID_LIMIT"
    assert payload["error"]


# ---------------------------------------------------------------------------
# geocode_result_from_candidate (pure helper)
# ---------------------------------------------------------------------------

def _candidate(**over):
    data = {
        "label": "Nakasero Market, Kampala, Uganda",
        "latitude": 0.3476,
        "longitude": 32.5825,
        "provider": "photon",
        "osm_type": "N",
        "osm_id": 12345,
    }
    data.update(over)
    return data


def test_candidate_valid_builds_resolved_result():
    from app.geo.services import geocode_result_from_candidate
    result = geocode_result_from_candidate(_candidate())
    assert result.resolved is True
    assert result.provider == "photon"
    assert result.latitude == pytest.approx(0.3476)
    assert result.longitude == pytest.approx(32.5825)
    assert result.display_name == "Nakasero Market, Kampala, Uganda"
    assert result.raw == {"osm_type": "N", "osm_id": 12345}


def test_candidate_keeps_only_osm_keys():
    """Provider-flavoured extras are never copied into raw."""
    from app.geo.services import geocode_result_from_candidate
    result = geocode_result_from_candidate(_candidate(
        confidence=0.9, city="Kampala", osm_type=None))
    assert result.raw == {"osm_id": 12345}  # None osm_type omitted


def test_candidate_missing_label_defaults_to_empty():
    from app.geo.services import geocode_result_from_candidate
    candidate = _candidate()
    del candidate["label"]
    result = geocode_result_from_candidate(candidate)
    assert result.display_name == ""


@pytest.mark.parametrize("provider", [None, "", "   ", "unresolved", 42])
def test_candidate_rejects_bad_provider(provider):
    from app.geo.services import geocode_result_from_candidate
    from app.utils.exceptions import ValidationError
    with pytest.raises(ValidationError):
        geocode_result_from_candidate(_candidate(provider=provider))


@pytest.mark.parametrize("bad_pair", [
    (91.0, 32.5825),        # latitude out of range
    (0.3476, 181.0),        # longitude out of range
    (float("nan"), 32.5825),  # not finite
    (float("inf"), 32.5825),  # not finite
    (True, 32.5825),        # bool is never a coordinate (UI-LOC-02A)
    ("0.3476", 32.5825),    # string is not numeric — never coerced
    (0.3476, None),         # missing coordinate
])
def test_candidate_rejects_bad_coordinates(bad_pair):
    from app.geo.services import geocode_result_from_candidate
    from app.utils.exceptions import ValidationError
    latitude, longitude = bad_pair
    with pytest.raises(ValidationError):
        geocode_result_from_candidate(
            _candidate(latitude=latitude, longitude=longitude))


@pytest.mark.parametrize("bad", [None, "Nakasero", 42, ["label"]])
def test_candidate_rejects_non_mapping(bad):
    from app.geo.services import geocode_result_from_candidate
    from app.utils.exceptions import ValidationError
    with pytest.raises(ValidationError):
        geocode_result_from_candidate(bad)


# ---------------------------------------------------------------------------
# Booking seam: search evidence is mandatory, gps/map unchanged
# ---------------------------------------------------------------------------

def _user_id(app, test_user):
    from app.extensions import db
    with app.app_context():
        merged = db.session.merge(test_user)
        uid = merged.id
        db.session.rollback()
        return uid


def _payload(**over):
    data = {
        "pickup_location": "Nakawa Riders Pickup Point",
        "dropoff_location": "Entebbe Airside Gate",
        "pickup_latitude": _PICKUP[0],
        "pickup_longitude": _PICKUP[1],
        "dropoff_latitude": _DROPOFF[0],
        "dropoff_longitude": _DROPOFF[1],
        "service_type": "on_demand",
        "pickup_time": "2026-12-31T10:00:00",
        "passenger_count": 2,
        "currency": "USD",
        "vehicle_class": "comfort",
        "payment_method": "cash",
        "idempotency_key": f"ui01-{uuid.uuid4().hex}",
    }
    data.update(over)
    return data


def _create(app, user_id, data):
    from app.transport.services.booking_service import BookingService
    with app.app_context():
        return BookingService().create_booking(
            user_id, data, request_id=f"test-{data['idempotency_key']}"
        )["data"]["booking_reference"]


def _snapshots(app, reference):
    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        booking = Booking.query.filter_by(
            booking_reference=reference, is_deleted=False
        ).first()
        assert booking is not None, f"no booking row for {reference}"
        pickup = dict(booking.pickup_location)
        dropoff = dict(booking.dropoff_location)
        db.session.rollback()
        return pickup, dropoff


def _count(app, key, user_id):
    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        count = Booking.query.filter_by(
            idempotency_key=key, user_id=user_id, is_deleted=False
        ).count()
        db.session.rollback()
        return count


def test_search_with_evidence_persists_forward_geocode_snapshot(
        app, test_user):
    """The endpoint result -> hidden-field echo -> helper -> builder
    path is the ONLY truthful way to persist source='search'."""
    user_id = _user_id(app, test_user)
    pickup_candidate = _candidate(
        latitude=_PICKUP[0], longitude=_PICKUP[1],
        label="Nakawa Riders Pickup Point, Kampala, Uganda")
    dropoff_candidate = _candidate(
        latitude=_DROPOFF[0], longitude=_DROPOFF[1],
        label="Entebbe Airside Gate, Entebbe, Uganda", osm_id=67890)
    data = _payload(
        pickup_source="search",
        pickup_geocode=json.dumps(pickup_candidate),
        dropoff_source="search",
        dropoff_geocode=json.dumps(dropoff_candidate),
    )
    reference = _create(app, user_id, data)

    pickup, dropoff = _snapshots(app, reference)
    assert pickup["source"] == "search"
    assert pickup["resolution_method"] == "forward_geocode"
    # H1: coordinates are exactly the submitted (same-candidate) ones.
    assert pickup["latitude"] == _PICKUP[0]
    assert pickup["longitude"] == _PICKUP[1]
    assert pickup["provenance"] is not None
    assert pickup["provenance"]["authority"] == "photon"
    assert pickup["provenance"]["reference"] == "N/12345"
    # pickup and dropoff are symmetric
    assert dropoff["source"] == "search"
    assert dropoff["resolution_method"] == "forward_geocode"
    assert dropoff["latitude"] == _DROPOFF[0]
    assert dropoff["longitude"] == _DROPOFF[1]
    assert dropoff["provenance"]["authority"] == "photon"
    assert dropoff["provenance"]["reference"] == "N/67890"


def test_search_without_evidence_fails_and_creates_no_row(
        app, test_user):
    """H2 preserved: a search claim without pickup_geocode provider
    evidence is a field-precise client error — no row is created."""
    from app.utils.exceptions import ValidationError

    user_id = _user_id(app, test_user)
    data = _payload(pickup_source="search")
    key = data["idempotency_key"]

    with app.app_context():
        with pytest.raises(ValidationError) as excinfo:
            from app.transport.services.booking_service import (
                BookingService)
            BookingService().create_booking(
                user_id, data, request_id=f"test-{key}")

    assert excinfo.value.field == "pickup_source"
    assert "pickup_geocode provider evidence" in str(excinfo.value)
    assert _count(app, key, user_id) == 0


def test_search_with_invalid_candidate_json_fails_and_creates_no_row(
        app, test_user):
    from app.utils.exceptions import ValidationError

    user_id = _user_id(app, test_user)
    data = _payload(pickup_source="search", pickup_geocode="not-json{")
    key = data["idempotency_key"]

    with app.app_context():
        with pytest.raises(ValidationError) as excinfo:
            from app.transport.services.booking_service import (
                BookingService)
            BookingService().create_booking(
                user_id, data, request_id=f"test-{key}")

    assert excinfo.value.field == "pickup_source"
    assert _count(app, key, user_id) == 0


def test_search_with_unresolved_provider_candidate_rejected(
        app, test_user):
    """An 'unresolved' echo carries no evidence and is never laundered
    into a provider identity."""
    from app.utils.exceptions import ValidationError

    user_id = _user_id(app, test_user)
    data = _payload(
        pickup_source="search",
        pickup_geocode=json.dumps(_candidate(provider="unresolved")),
    )
    key = data["idempotency_key"]

    with app.app_context():
        with pytest.raises(ValidationError) as excinfo:
            from app.transport.services.booking_service import (
                BookingService)
            BookingService().create_booking(
                user_id, data, request_id=f"test-{key}")

    assert excinfo.value.field == "pickup_source"
    assert _count(app, key, user_id) == 0


def test_gps_and_map_without_evidence_still_works(app, test_user):
    """Regression: direct-coordinate sources never need evidence."""
    user_id = _user_id(app, test_user)
    data = _payload(pickup_source="gps", dropoff_source="map")
    reference = _create(app, user_id, data)

    pickup, dropoff = _snapshots(app, reference)
    assert pickup["source"] == "gps"
    assert pickup["resolution_method"] == "browser_geolocation"
    assert pickup["provenance"] is None
    assert dropoff["source"] == "map"
    assert dropoff["resolution_method"] == "map_pin"
    assert dropoff["provenance"] is None
