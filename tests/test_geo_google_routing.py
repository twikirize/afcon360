"""Contract tests for the Google Maps Directions routing adapter."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from app.geo.interfaces import GeoPoint

KAMPALA = GeoPoint(0.3476, 32.5825)
ENTEBBE = GeoPoint(0.0515, 32.4467)
GOOGLE_DISTANCE_M = 45_200.0
GOOGLE_DURATION_S = 3240.0
GOOGLE_POLYLINE = "_p~iF~ps|U_ulLnnqC"


class _FakeGoogleHandler(BaseHTTPRequestHandler):
    requests_seen = []
    mode = "ok"

    def log_message(self, *args):
        pass

    def do_GET(self):
        type(self).requests_seen.append(self.path)
        if self.mode == "error":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")
            return
        if self.mode == "denied":
            body = json.dumps({
                "status": "REQUEST_DENIED",
                "routes": [],
            }).encode()
        else:
            body = json.dumps({
                "status": "OK",
                "routes": [{
                    "legs": [{
                        "distance": {"value": GOOGLE_DISTANCE_M},
                        "duration": {"value": GOOGLE_DURATION_S},
                    }],
                    "overview_polyline": {"points": GOOGLE_POLYLINE},
                }],
            }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def fake_google():
    handler = _FakeGoogleHandler
    handler.requests_seen = []
    handler.mode = "ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/maps/api", handler
    server.shutdown()
    thread.join(timeout=5)


def _google(base_url, **overrides):
    from app.geo.providers.google import GoogleMapsConfig, GoogleMapsRouter
    kwargs = {"base_url": base_url, "api_key": "test-key", "enabled": True}
    kwargs.update(overrides)
    return GoogleMapsRouter(GoogleMapsConfig(**kwargs))


def test_google_normalizes_units_and_polyline(fake_google):
    base_url, _ = fake_google
    result = _google(base_url).route(KAMPALA, ENTEBBE)
    assert result.resolved is True
    assert result.provider == "google"
    assert result.distance_m == pytest.approx(GOOGLE_DISTANCE_M)
    assert result.duration_s == pytest.approx(GOOGLE_DURATION_S)
    assert (result.geometry[0].latitude,
            result.geometry[0].longitude) == pytest.approx((38.5, -120.2))


def test_google_wire_uses_origin_destination_mode_and_key(fake_google):
    base_url, handler = fake_google
    handler.requests_seen = []
    _google(base_url).route(KAMPALA, ENTEBBE, profile="pedestrian")
    parsed = urlparse(handler.requests_seen[-1])
    query = parse_qs(parsed.query)
    assert parsed.path == "/maps/api/directions/json"
    assert query["origin"] == ["0.3476,32.5825"]
    assert query["destination"] == ["0.0515,32.4467"]
    assert query["mode"] == ["walking"]
    assert query["key"] == ["test-key"]


@pytest.mark.parametrize("profile,mode", [
    ("auto", "driving"),
    ("driving", "driving"),
    ("pedestrian", "walking"),
    ("bicycle", "bicycling"),
])
def test_google_profile_mapping(fake_google, profile, mode):
    base_url, handler = fake_google
    handler.requests_seen = []
    assert _google(base_url).route(KAMPALA, ENTEBBE,
                                   profile=profile).resolved is True
    query = parse_qs(urlparse(handler.requests_seen[-1]).query)
    assert query["mode"] == [mode]


def test_google_motorcycle_is_truthful_miss(fake_google):
    base_url, handler = fake_google
    before = len(handler.requests_seen)
    result = _google(base_url).route(KAMPALA, ENTEBBE, profile="motorcycle")
    assert result.resolved is False
    assert result.provider == "google"
    assert len(handler.requests_seen) == before


def test_google_http_error_is_unresolved(fake_google):
    base_url, handler = fake_google
    handler.mode = "error"
    try:
        assert _google(base_url).route(KAMPALA, ENTEBBE).resolved is False
    finally:
        handler.mode = "ok"


def test_google_request_denied_is_unresolved(fake_google):
    base_url, handler = fake_google
    handler.mode = "denied"
    try:
        result = _google(base_url).route(KAMPALA, ENTEBBE)
    finally:
        handler.mode = "ok"
    assert result.resolved is False
    assert result.provider == "google"


def test_google_disabled_never_touches_network(monkeypatch):
    from app.geo.providers.google import GoogleMapsConfig, GoogleMapsRouter
    called = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: called.append(1))
    router = GoogleMapsRouter(GoogleMapsConfig())
    assert router.is_available() is False
    assert router.route(KAMPALA, ENTEBBE).resolved is False
    assert called == []


def test_decode_polyline_known_example():
    from app.geo.providers.google import decode_polyline
    points = decode_polyline(GOOGLE_POLYLINE)
    assert [(round(p.latitude, 3), round(p.longitude, 3))
            for p in points] == [
        (38.5, -120.2), (40.7, -120.95)]
