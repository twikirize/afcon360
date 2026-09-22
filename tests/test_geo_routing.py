"""GEO routing adapter — contract tests (routing node).

Proves the routing contract against a controlled localhost fake Valhalla
server (real HTTP round-trip through OUR adapter code). The fake is
explicitly NOT live routing: it serves canned responses so request
serialization, error mapping, unit normalization, and coordinate order
are genuinely exercised. Live Valhalla verification is recorded
separately as unavailable (no local provider in this environment).
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from app.geo.interfaces import GeoPoint
from app.geo.services import (
    RoutingService,
    straight_line_distance_m,
)
from app.utils.exceptions import ValidationError


KAMPALA = GeoPoint(0.3476, 32.5825)
ENTEBBE = GeoPoint(0.0515, 32.4467)
# Canned road values: deliberately NOT the straight-line ones so tests
# prove road vs straight-line distinction (straight ≈ 36.2 km).
ROAD_LENGTH_KM = 45.2
ROAD_TIME_S = 3240.0


# --- test-only helpers (clearly labeled, never production) -------------------

def _encode_polyline(points, precision=6):
    """Minimal encoder for building fake-server fixtures only."""
    factor = 10 ** precision
    out = []
    prev_lat, prev_lng = 0, 0
    for lat, lng in points:
        lat_i = int(round(lat * factor))
        lng_i = int(round(lng * factor))
        for delta in (lat_i - prev_lat, lng_i - prev_lng):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev_lat, prev_lng = lat_i, lng_i
    return "".join(out)


FAKE_SHAPE = _encode_polyline(
    [(0.3476, 32.5825), (0.2000, 32.5100), (0.0515, 32.4467)])

FAKE_TRIP = {
    "trip": {
        "summary": {"length": ROAD_LENGTH_KM, "time": ROAD_TIME_S},
        "legs": [{"shape": FAKE_SHAPE}],
        "status": 0,
    }
}


class _FakeValhallaHandler(BaseHTTPRequestHandler):
    """Controlled stand-in. Records request bodies for order assertions."""
    bodies = []
    mode = "ok"  # ok | error | malformed | slow

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        type(self).bodies.append((self.path, json.loads(body or b"{}")))
        if self.mode == "error":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")
        elif self.mode == "malformed":
            payload = json.dumps({"unexpected": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.mode == "slow":
            import time
            time.sleep(2.0)
            payload = json.dumps(FAKE_TRIP).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except Exception:
                pass  # client timed out and went away: expected
        else:
            payload = json.dumps(FAKE_TRIP).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)


@pytest.fixture(scope="module")
def fake_valhalla():
    _FakeValhallaHandler.bodies = []
    _FakeValhallaHandler.mode = "ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeValhallaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield (f"http://127.0.0.1:{server.server_port}",
           _FakeValhallaHandler)
    server.shutdown()
    thread.join(timeout=5)


def _router(base_url, **overrides):
    from app.geo.providers.valhalla import ValhallaConfig, ValhallaRouter
    kwargs = {"base_url": base_url, "enabled": True}
    kwargs.update(overrides)
    return ValhallaRouter(ValhallaConfig(**kwargs))


# --- valid route: normalized road contract -------------------------------------

def test_valid_route_returns_normalized_road_result(fake_valhalla):
    base_url, _ = fake_valhalla
    result = _router(base_url).route(KAMPALA, ENTEBBE)
    assert result.resolved is True
    assert result.provider == "valhalla"
    assert result.distance_m == pytest.approx(ROAD_LENGTH_KM * 1000.0)
    assert result.duration_s == pytest.approx(ROAD_TIME_S)
    assert [ (p.latitude, p.longitude) for p in result.geometry ] == [
        pytest.approx((0.3476, 32.5825)),
        pytest.approx((0.2000, 32.5100)),
        pytest.approx((0.0515, 32.4467)),
    ]


def test_road_distance_is_not_straight_line(fake_valhalla):
    base_url, _ = fake_valhalla
    result = _router(base_url).route(KAMPALA, ENTEBBE)
    straight = straight_line_distance_m(KAMPALA, ENTEBBE)
    assert result.distance_m != pytest.approx(straight)
    assert result.distance_m > straight  # road detour exceeds great-circle
    assert result.provider != "haversine-fallback"


def test_request_uses_lat_lon_order_and_costing(fake_valhalla):
    base_url, handler = fake_valhalla
    handler.bodies = []
    _router(base_url).route(KAMPALA, ENTEBBE, profile="auto")
    assert handler.bodies, "adapter must POST to the provider"
    path, body = handler.bodies[-1]
    assert path == "/route"
    assert body["locations"][0] == {"lat": 0.3476, "lon": 32.5825}
    assert body["locations"][1] == {"lat": 0.0515, "lon": 32.4467}
    assert body["costing"] == "auto"


# --- invalid input ---------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    GeoPoint(91.0, 0.0),
    GeoPoint(0.0, 181.0),
    GeoPoint(float("nan"), 0.0),
])
def test_invalid_coordinates_raise_validation_error(fake_valhalla, bad):
    base_url, handler = fake_valhalla
    before = len(handler.bodies)
    router = _router(base_url)
    with pytest.raises(ValidationError):
        router.route(bad, ENTEBBE)
    with pytest.raises(ValidationError):
        router.route(KAMPALA, bad)
    assert len(handler.bodies) == before  # never touches the network


# --- unavailable / failure truthfulness ---------------------------------------------

def test_disabled_adapter_never_touches_network(monkeypatch):
    from app.geo.providers.valhalla import ValhallaRouter
    posted = []
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: posted.append((a, k)))
    router = ValhallaRouter()  # disabled by default
    assert router.is_available() is False
    result = router.route(KAMPALA, ENTEBBE)
    assert result.resolved is False
    assert posted == []


def test_http_error_is_unresolved(fake_valhalla):
    base_url, handler = fake_valhalla
    handler.mode = "error"
    try:
        result = _router(base_url).route(KAMPALA, ENTEBBE)
    finally:
        handler.mode = "ok"
    assert result.resolved is False
    assert result.provider == "valhalla"


def test_malformed_response_is_unresolved(fake_valhalla):
    base_url, handler = fake_valhalla
    handler.mode = "malformed"
    try:
        result = _router(base_url).route(KAMPALA, ENTEBBE)
    finally:
        handler.mode = "ok"
    assert result.resolved is False


def test_timeout_is_unresolved(fake_valhalla):
    base_url, handler = fake_valhalla
    handler.mode = "slow"
    try:
        result = _router(base_url, timeout_s=0.2).route(KAMPALA, ENTEBBE)
    finally:
        handler.mode = "ok"
    assert result.resolved is False


# --- deferred surface -----------------------------------------------------------------

def test_matrix_returns_unresolved_deferred(fake_valhalla):
    base_url, _ = fake_valhalla
    table = _router(base_url).matrix([KAMPALA], [ENTEBBE])
    assert table[0][0].resolved is False


# --- wiring factory ----------------------------------------------------------------------

def test_build_routing_service_disabled_keeps_fallback():
    from app.geo.config import GeoConfig
    from app.geo.services import build_routing_service
    from app.geo.providers.photon import PhotonConfig
    from app.geo.providers.tiles import TileProviderConfig
    from app.geo.providers.valhalla import ValhallaConfig
    config = GeoConfig(valhalla=ValhallaConfig(),
                       photon=PhotonConfig(),
                       tiles=TileProviderConfig())
    service = build_routing_service(config)
    assert service.provider_name == "unresolved"
    result = service.route(KAMPALA, ENTEBBE)
    assert result.resolved is False
    assert result.provider == "haversine-fallback"


def test_build_routing_service_enabled_wires_adapter_without_io(fake_valhalla):
    from app.geo.config import GeoConfig
    from app.geo.providers.photon import PhotonConfig
    from app.geo.providers.tiles import TileProviderConfig
    from app.geo.providers.valhalla import ValhallaConfig
    base_url, handler = fake_valhalla
    before = len(handler.bodies)
    from app.geo.services import build_routing_service
    config = GeoConfig(
        valhalla=ValhallaConfig(base_url=base_url, enabled=True),
        photon=PhotonConfig(), tiles=TileProviderConfig())
    service = build_routing_service(config)
    assert service.provider_name == "valhalla"
    assert len(handler.bodies) == before  # wiring performs no I/O
    assert isinstance(service, RoutingService)


# --- polyline decoder truth ---------------------------------------------------------------

def test_polyline_decoder_against_known_vector():
    from app.geo.providers.valhalla import _decode_polyline
    # Canonical precision-5 example from the encoded-polyline spec.
    points = _decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", precision=5)
    assert [(round(lat, 3), round(lng, 3)) for lat, lng in points] == [
        (38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
