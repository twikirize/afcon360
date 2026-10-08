"""GEO reverse lookup endpoint — contract tests.

Proves through the REAL /geo/api/reverse (controlled localhost fakes;
never live providers, no credentials):

  * anonymous reverse resolves a human-readable identity (Discovery);
  * invalid coordinates (missing / non-numeric / out-of-range / NaN /
    Inf) are 400 INVALID_COORDINATES without provider I/O;
  * double provider failure degrades to presentable=false with success
    true (coordinates stay the caller's truth; no fabricated identity);
  * Photon answers when Geoapify fails (existing secondary);
  * non-presentable provider classes (unknown type / water body) surface
    as display_name=None + presentable=false;
  * the API key never appears in any payload; attribution follows the
    answering provider; rate limiting answers 429 JSON.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

URL = "/geo/api/reverse"


def _geoapify_feature(lon, lat, formatted, result_type="amenity",
                      ocean=None):
    properties = {
        "lon": lon, "lat": lat, "formatted": formatted,
        "country": "Uganda", "country_code": "ug",
        "result_type": result_type,
        "rank": {"confidence": 1, "match_type": "full_match"},
        "datasource": {"sourcename": "openstreetmap"},
    }
    if ocean is not None:
        properties["ocean"] = ocean
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


GEOAPIFY_REVERSE_OK = {
    "type": "FeatureCollection",
    "features": [_geoapify_feature(
        32.58207, 0.31693,
        "Sheraton Kampala Hotel, Kampala, Central Kampala, Uganda")],
}

GEOAPIFY_REVERSE_WATER = {
    "type": "FeatureCollection",
    "features": [_geoapify_feature(
        -18.914856, -34.006681, "", result_type="unknown",
        ocean="South Atlantic Ocean")],
}


class _GeoapifyHandler(BaseHTTPRequestHandler):
    calls = []
    mode = "ok"  # ok | empty | error | water

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
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = json.dumps(
                GEOAPIFY_REVERSE_WATER if self.mode == "water"
                else GEOAPIFY_REVERSE_OK).encode()
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
            return
        if self.mode == "empty":
            body = json.dumps(
                {"type": "FeatureCollection", "features": []}).encode()
        else:
            body = json.dumps({
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Point",
                                 "coordinates": [32.5825, 0.3476]},
                    "properties": {"name": "Nakasero Market",
                                   "city": "Kampala",
                                   "country": "Uganda"},
                }],
            }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def fake_geoapify_rev():
    _GeoapifyHandler.calls = []
    _GeoapifyHandler.mode = "ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GeoapifyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield (f"http://127.0.0.1:{server.server_port}", _GeoapifyHandler)
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def fake_photon_rev():
    _PhotonHandler.calls = []
    _PhotonHandler.mode = "ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PhotonHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield (f"http://127.0.0.1:{server.server_port}", _PhotonHandler)
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture()
def reverse_env(monkeypatch, fake_geoapify_rev, fake_photon_rev):
    geo_url, geo_handler = fake_geoapify_rev
    pho_url, pho_handler = fake_photon_rev
    geo_handler.calls = []
    geo_handler.mode = "ok"
    pho_handler.calls = []
    pho_handler.mode = "ok"
    monkeypatch.setenv("GEOAPIFY_BASE_URL", geo_url)
    monkeypatch.setenv("GEOAPIFY_API_KEY", "reverse-test-key")
    monkeypatch.setenv("GEOAPIFY_ENABLED", "true")
    monkeypatch.setenv("GEO_PHOTON_URL", pho_url)
    monkeypatch.setenv("GEO_PHOTON_ENABLED", "true")
    return geo_handler, pho_handler


def _qs(lat="0.3177137", lon="32.5813539"):
    return {"lat": lat, "lon": lon}


def test_anonymous_reverse_returns_identity(
        anonymous_client, reverse_env):
    geo_handler, pho_handler = reverse_env
    resp = anonymous_client.get(URL, query_string=_qs())
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "geoapify"
    assert payload["latitude"] == pytest.approx(0.3177137)
    assert payload["longitude"] == pytest.approx(32.5813539)
    assert payload["display_name"] == (
        "Sheraton Kampala Hotel, Kampala, Central Kampala, Uganda")
    assert payload["presentable"] is True
    assert "Geoapify" in (payload["attribution"] or "")
    assert pho_handler.calls == []  # useful answer: no fallback call
    path, params = geo_handler.calls[-1]
    assert path == "/v1/geocode/reverse"
    assert params.get("lat") == ["0.3177137"]
    assert params.get("lon") == ["32.5813539"]
    assert params.get("format") == ["geojson"]


@pytest.mark.parametrize("lat,lon", [
    (None, "32.58"), ("0.31", None), ("abc", "32.58"), ("0.31", "xyz"),
    ("91.0", "32.58"), ("0.31", "181.0"), ("nan", "32.58"),
    ("inf", "32.58"), ("0.31", "-inf"), ("", ""),
])
def test_invalid_coordinates_rejected_without_io(
        anonymous_client, reverse_env, monkeypatch, lat, lon):
    import requests as _requests
    geo_handler, _ = reverse_env
    posted = []
    monkeypatch.setattr(
        _requests, "get", lambda *a, **k: posted.append((a, k)))
    qs = {}
    if lat is not None:
        qs["lat"] = lat
    if lon is not None:
        qs["lon"] = lon
    resp = anonymous_client.get(URL, query_string=qs)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_COORDINATES"
    assert posted == []
    assert geo_handler.calls == []


def test_double_failure_is_unpresentable(anonymous_client, reverse_env):
    geo_handler, pho_handler = reverse_env
    geo_handler.mode = "error"
    pho_handler.mode = "error"
    resp = anonymous_client.get(URL, query_string=_qs())
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "unresolved"
    assert payload["display_name"] is None
    assert payload["presentable"] is False
    assert payload["attribution"] is None


def test_photon_fallback_reverse(anonymous_client, reverse_env):
    geo_handler, pho_handler = reverse_env
    geo_handler.mode = "error"
    resp = anonymous_client.get(URL, query_string=_qs())
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "photon"
    assert payload["display_name"] == "Nakasero Market, Kampala, Uganda"
    assert payload["presentable"] is True
    assert pho_handler.calls != []


def test_water_class_is_not_presentable(anonymous_client, reverse_env):
    """Provider-resolved but not displayable: unknown type + water body
    surfaces as display_name=None, never as a rider-facing place."""
    geo_handler, _ = reverse_env
    geo_handler.mode = "water"
    resp = anonymous_client.get(URL, query_string=_qs(lat="0.0", lon="-30.0"))
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "unresolved"
    assert payload["display_name"] is None
    assert payload["presentable"] is False


def test_api_key_never_in_response(anonymous_client, reverse_env):
    resp = anonymous_client.get(URL, query_string=_qs())
    assert resp.status_code == 200
    assert "reverse-test-key" not in resp.get_data(as_text=True)


def test_rate_limit_returns_429_json(authenticated_client, reverse_env):
    from app.utils.rate_limiting import clear_rate_limits
    clear_rate_limits()
    try:
        last = None
        for _ in range(61):
            last = authenticated_client.get(URL, query_string=_qs())
        assert last is not None
        assert last.status_code == 429
        assert last.get_json()["code"] == "RATE_LIMITED"
    finally:
        clear_rate_limits()
