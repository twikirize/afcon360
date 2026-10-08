"""GEO provider chain at the HTTP endpoint — controlled tests.

Proves through the REAL /geo/api/geocode (no browser stubbing here, no
live providers, no credentials) with controlled localhost fakes:

  * Geoapify-first: both configured -> provider "geoapify", Photon untouched;
  * fallback: Geoapify fails -> Photon attempted -> provider "photon";
  * double failure -> provider "unresolved", results [], success true;
  * attribution per answering provider; API key never in any payload;
  * a Geoapify echo persists the canonical search snapshot with
    provenance.authority == "geoapify".
"""

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

URL = "/geo/api/geocode"
_PICKUP = (0.3136, 32.5811)
_DROPOFF = (0.3476, 32.5825)


def _geoapify_feature(lon, lat, formatted, match_type="full_match",
                      confidence=1.0):
    return {
        "type": "Feature",
        "properties": {
            "datasource": {"sourcename": "openstreetmap"},
            "country": "Uganda",
            "country_code": "ug",
            "state": "Central Region",
            "city": "Kampala",
            "lon": lon,
            "lat": lat,
            "formatted": formatted,
            "result_type": "locality",
            "rank": {"confidence": confidence,
                     "match_type": match_type},
            "place_id": "51ab791e4a0f7e5ec059b7c8a1d2f3a0147f00101f9011a2b0000000000c00208",
            "name": formatted.split(",")[0],
        },
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


GEOAPIFY_OK = {
    "type": "FeatureCollection",
    "features": [
        _geoapify_feature(32.5813539, 0.3177137,
                          "Kampala, Central Region, Uganda"),
        _geoapify_feature(32.5877299, 0.3365912,
                          "Acacia Mall, Kampala, Uganda"),
    ],
}


GEOAPIFY_WEAK = {
    "type": "FeatureCollection",
    "features": [
        _geoapify_feature(32.5813539, 0.3177137,
                          "Kampala, Central Region, Uganda",
                          match_type="inner_match", confidence=0.4),
    ],
}


def _photon_feature(lon, lat, name):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"name": name, "city": "Kampala",
                       "country": "Uganda", "osm_id": 999,
                       "osm_type": "N"},
    }


PHOTON_OK = {
    "type": "FeatureCollection",
    "features": [_photon_feature(32.5825, 0.3476, "Nakasero Market")],
}


class _GeoapifyHandler(BaseHTTPRequestHandler):
    calls = []
    mode = "ok"  # ok | empty | error | weak

    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        type(self).calls.append((parsed.path, parse_qs(parsed.query)))
        if self.mode == "error":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")
        elif self.mode == "empty":
            body = json.dumps(
                {"type": "FeatureCollection", "features": []}).encode()
        elif self.mode == "weak":
            body = json.dumps(GEOAPIFY_WEAK).encode()
        else:
            body = json.dumps(GEOAPIFY_OK).encode()
        if self.mode != "error":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


class _PhotonHandler(BaseHTTPRequestHandler):
    calls = []
    mode = "ok"  # ok | empty | error

    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        type(self).calls.append((parsed.path, parse_qs(parsed.query)))
        if self.mode == "error":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")
        elif self.mode == "empty":
            body = json.dumps(
                {"type": "FeatureCollection", "features": []}).encode()
        else:
            body = json.dumps(PHOTON_OK).encode()
        if self.mode != "error":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


@pytest.fixture(scope="module")
def fake_geoapify_ep():
    _GeoapifyHandler.calls = []
    _GeoapifyHandler.mode = "ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GeoapifyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield (f"http://127.0.0.1:{server.server_port}", _GeoapifyHandler)
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def fake_photon_ep():
    _PhotonHandler.calls = []
    _PhotonHandler.mode = "ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PhotonHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield (f"http://127.0.0.1:{server.server_port}", _PhotonHandler)
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture()
def chain_env(monkeypatch, fake_geoapify_ep, fake_photon_ep):
    geo_url, geo_handler = fake_geoapify_ep
    pho_url, pho_handler = fake_photon_ep
    geo_handler.calls = []
    geo_handler.mode = "ok"
    pho_handler.calls = []
    pho_handler.mode = "ok"
    monkeypatch.setenv("GEOAPIFY_BASE_URL", geo_url)
    monkeypatch.setenv("GEOAPIFY_API_KEY", "endpoint-test-key")
    monkeypatch.setenv("GEOAPIFY_ENABLED", "true")
    monkeypatch.setenv("GEO_PHOTON_URL", pho_url)
    monkeypatch.setenv("GEO_PHOTON_ENABLED", "true")
    return geo_handler, pho_handler


def test_geoapify_first_photon_untouched(authenticated_client, chain_env):
    geo_handler, pho_handler = chain_env
    resp = authenticated_client.get(URL, query_string={"q": "Kampala"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "geoapify"
    assert len(payload["results"]) == 2
    first = payload["results"][0]
    assert first["label"] == "Kampala, Central Region, Uganda"
    assert first["latitude"] == pytest.approx(0.3177137)
    assert first["longitude"] == pytest.approx(32.5813539)
    assert first["provider"] == "geoapify"
    assert "osm_type" not in first and "osm_id" not in first
    assert "Geoapify" in (payload["attribution"] or "")
    assert pho_handler.calls == []
    path, params = geo_handler.calls[-1]
    assert path == "/v1/geocode/search"
    assert params.get("text") == ["Kampala"]
    assert params.get("format") == ["geojson"]


def test_fallback_to_photon_on_geoapify_failure(
        authenticated_client, chain_env):
    geo_handler, pho_handler = chain_env
    geo_handler.mode = "error"
    resp = authenticated_client.get(URL, query_string={"q": "Kampala"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "photon"
    assert len(payload["results"]) == 1
    assert payload["results"][0]["label"] == "Nakasero Market, Kampala, Uganda"
    assert pho_handler.calls != []
    assert "Geoapify" not in (payload["attribution"] or "")
    assert "OpenStreetMap" in (payload["attribution"] or "")


def test_double_failure_is_unresolved(authenticated_client, chain_env):
    geo_handler, pho_handler = chain_env
    geo_handler.mode = "error"
    pho_handler.mode = "error"
    resp = authenticated_client.get(URL, query_string={"q": "Kampala"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "unresolved"
    assert payload["results"] == []
    assert payload["attribution"] is None


def test_valid_empty_does_not_call_photon(authenticated_client, chain_env):
    """Policy C: Geoapify valid success with zero useful candidates is an
    honest no-result — Photon must NOT be queried automatically."""
    geo_handler, pho_handler = chain_env
    geo_handler.mode = "empty"
    resp = authenticated_client.get(URL, query_string={"q": "Nowhere XYZ"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "unresolved"
    assert payload["results"] == []
    assert pho_handler.calls == []


def test_weak_geoapify_hit_gets_photon_supplement(
        authenticated_client, chain_env):
    """Policy D: one weak Geoapify hit -> Photon appended after it, each
    carrying its answering provider name."""
    geo_handler, pho_handler = chain_env
    geo_handler.mode = "weak"
    resp = authenticated_client.get(URL, query_string={"q": "Kampala"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert [item["provider"] for item in payload["results"]] == [
        "geoapify", "photon"]
    assert payload["provider"] == "geoapify"
    assert pho_handler.calls != []


def test_single_character_query_needs_no_provider(
        authenticated_client, chain_env, monkeypatch):
    import requests as _requests
    geo_handler, pho_handler = chain_env
    posted = []
    monkeypatch.setattr(
        _requests, "get", lambda *a, **k: posted.append((a, k)))
    resp = authenticated_client.get(URL, query_string={"q": "K"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "unresolved"
    assert payload["results"] == []
    assert posted == []
    assert geo_handler.calls == []
    assert pho_handler.calls == []


def test_rate_limit_returns_429_json(authenticated_client, chain_env):
    from app.utils.rate_limiting import clear_rate_limits
    clear_rate_limits()
    try:
        last = None
        for _ in range(61):
            last = authenticated_client.get(URL, query_string={"q": "Kampala"})
        assert last is not None
        assert last.status_code == 429
        payload = last.get_json()
        assert payload["success"] is False
        assert payload["code"] == "RATE_LIMITED"
    finally:
        clear_rate_limits()


def test_api_key_never_in_response(authenticated_client, chain_env):
    resp = authenticated_client.get(URL, query_string={"q": "Kampala"})
    assert resp.status_code == 200
    assert "endpoint-test-key" not in resp.get_data(as_text=True)


def test_health_reports_geoapify_booleans_not_key(
        authenticated_client, chain_env):
    resp = authenticated_client.get("/geo/api/health")
    assert resp.status_code == 200
    adapter = resp.get_json()["adapters"]["geoapify"]
    assert adapter == {"enabled": True, "configured": True}
    assert "endpoint-test-key" not in resp.get_data(as_text=True)


# --- booking seam with a Geoapify echo ---------------------------------------

def _user_id(app, test_user):
    from app.extensions import db
    with app.app_context():
        merged = db.session.merge(test_user)
        uid = merged.id
        db.session.rollback()
        return uid


def _payload(**over):
    data = {
        "pickup_location": "Kampala search pickup",
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
        "idempotency_key": f"chain-{uuid.uuid4().hex}",
    }
    data.update(over)
    return data


def test_geoapify_echo_persists_canonical_snapshot(app, test_user):
    from app.transport.services.booking_service import BookingService
    user_id = _user_id(app, test_user)
    candidate = {
        "label": "Kampala, Central Region, Uganda",
        "latitude": _PICKUP[0],
        "longitude": _PICKUP[1],
        "provider": "geoapify",
    }
    data = _payload(pickup_location="Kampala, Central Region, Uganda",
                    pickup_source="search",
                    pickup_geocode=json.dumps(candidate),
                    dropoff_source="map")
    with app.app_context():
        reference = BookingService().create_booking(
            user_id, data,
            request_id=f"test-{data['idempotency_key']}",
        )["data"]["booking_reference"]
    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        booking = Booking.query.filter_by(
            booking_reference=reference, is_deleted=False).first()
        assert booking is not None
        pickup = dict(booking.pickup_location)
        db.session.rollback()
    assert sorted(pickup.keys()) == sorted([
        "latitude", "longitude", "source", "resolution_method",
        "provenance", "label", "display_name", "identity_status",
        "area", "accuracy_m", "confidence", "observed_at", "resolved_at",
    ])
    assert pickup["source"] == "search"
    assert pickup["resolution_method"] == "forward_geocode"
    assert pickup["provenance"] == {"authority": "geoapify",
                                    "reference": None}
    assert pickup["label"] == "Kampala, Central Region, Uganda"
    assert pickup["display_name"] == "Kampala, Central Region, Uganda"
    assert pickup["identity_status"] == "unverified"
    assert "geoapify_" not in json.dumps(pickup)
