"""Contract tests for the hosted routing providers and provider chain.

The fakes are localhost HTTP servers: request serialization, coordinate
order, unit conversion, profile mapping, and fallback behavior are really
exercised without depending on a live engine.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from app.geo.interfaces import GeoPoint, RouteResult
from app.geo.services import RoutingService, straight_line_distance_m
from app.utils.exceptions import ValidationError

KAMPALA = GeoPoint(0.3476, 32.5825)
ENTEBBE = GeoPoint(0.0515, 32.4467)
OSRM_DISTANCE_M = 45_200.0
OSRM_DURATION_S = 3240.0
GEOAPIFY_DISTANCE_M = 41_900.0
GEOAPIFY_DURATION_S = 2640.0


class _FakeOSRMHandler(BaseHTTPRequestHandler):
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
        if self.mode == "malformed":
            body = json.dumps({"code": "Ok", "routes": []}).encode()
        else:
            body = json.dumps({
                "code": "Ok",
                "routes": [{
                    "distance": OSRM_DISTANCE_M,
                    "duration": OSRM_DURATION_S,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [32.5825, 0.3476],
                            [32.5000, 0.2000],
                            [32.4467, 0.0515],
                        ],
                    },
                }],
            }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _FakeGraphHopperHandler(BaseHTTPRequestHandler):
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
        body = json.dumps({
            "paths": [{
                "distance": OSRM_DISTANCE_M,
                "time": OSRM_DURATION_S * 1000.0,
                "points": {
                    "type": "LineString",
                    "coordinates": [
                        [32.5825, 0.3476],
                        [32.5000, 0.2000],
                        [32.4467, 0.0515],
                    ],
                },
            }],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _FakeORSHandler(BaseHTTPRequestHandler):
    requests_seen = []
    bodies = []
    auth = []
    mode = "ok"

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        type(self).requests_seen.append(self.path)
        type(self).bodies.append(json.loads(raw))
        type(self).auth.append(self.headers.get("Authorization", ""))
        if self.mode == "error":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")
            return
        body = json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {
                    "summary": {
                        "distance": GEOAPIFY_DISTANCE_M,
                        "duration": GEOAPIFY_DURATION_S,
                    },
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [32.5825, 0.3476],
                        [32.5000, 0.2000],
                        [32.4467, 0.0515],
                    ],
                },
            }],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _FakeGeoapifyHandler(BaseHTTPRequestHandler):
    requests_seen = []
    mode = "ok"

    def log_message(self, *args):
        pass

    def do_GET(self):
        type(self).requests_seen.append(self.path)
        if self.mode == "error":
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"unavailable")
            return
        body = json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {
                    "distance": GEOAPIFY_DISTANCE_M,
                    "time": GEOAPIFY_DURATION_S,
                },
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [[
                        [32.5825, 0.3476],
                        [32.5000, 0.2000],
                        [32.4467, 0.0515],
                    ]],
                },
            }],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start(handler_cls):
    handler_cls.requests_seen = []
    handler_cls.mode = "ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@pytest.fixture(scope="module")
def fake_osrm():
    server, thread = _start(_FakeOSRMHandler)
    yield f"http://127.0.0.1:{server.server_port}", _FakeOSRMHandler
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def fake_geoapify():
    server, thread = _start(_FakeGeoapifyHandler)
    yield f"http://127.0.0.1:{server.server_port}", _FakeGeoapifyHandler
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def fake_graphhopper():
    server, thread = _start(_FakeGraphHopperHandler)
    yield f"http://127.0.0.1:{server.server_port}", _FakeGraphHopperHandler
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def fake_ors():
    server, thread = _start(_FakeORSHandler)
    yield f"http://127.0.0.1:{server.server_port}", _FakeORSHandler
    server.shutdown()
    thread.join(timeout=5)


def _osrm(base_url, **overrides):
    from app.geo.providers.osrm import OSRMConfig, OSRMRouter
    kwargs = {"base_url": base_url, "enabled": True}
    kwargs.update(overrides)
    return OSRMRouter(OSRMConfig(**kwargs))


def _geoapify(base_url, **overrides):
    from app.geo.providers.geoapify import GeoapifyConfig
    from app.geo.providers.geoapify_routing import GeoapifyRouter
    kwargs = {"base_url": base_url, "api_key": "test-key", "enabled": True}
    kwargs.update(overrides)
    return GeoapifyRouter(GeoapifyConfig(**kwargs))


def test_osrm_normalizes_units_and_axis(fake_osrm):
    base_url, _ = fake_osrm
    result = _osrm(base_url).route(KAMPALA, ENTEBBE)
    assert result.resolved is True
    assert result.provider == "osrm"
    assert result.distance_m == pytest.approx(OSRM_DISTANCE_M)
    assert result.duration_s == pytest.approx(OSRM_DURATION_S)
    assert (result.geometry[0].latitude,
            result.geometry[0].longitude) == pytest.approx((0.3476, 32.5825))
    assert result.distance_m > straight_line_distance_m(KAMPALA, ENTEBBE)


def test_osrm_wire_uses_lon_lat_path_and_geojson(fake_osrm):
    base_url, handler = fake_osrm
    handler.requests_seen = []
    _osrm(base_url).route(KAMPALA, ENTEBBE)
    parsed = urlparse(handler.requests_seen[-1])
    wire_path = parsed.path
    if parsed.params:
        wire_path += ";" + parsed.params
    assert wire_path == (
        "/route/v1/driving/32.5825,0.3476;32.4467,0.0515")
    assert parse_qs(parsed.query)["geometries"] == ["geojson"]


def test_osrm_unmapped_motorcycle_is_truthful_miss(fake_osrm):
    base_url, handler = fake_osrm
    before = len(handler.requests_seen)
    result = _osrm(base_url).route(KAMPALA, ENTEBBE, profile="motorcycle")
    assert result.resolved is False
    assert result.provider == "osrm"
    assert len(handler.requests_seen) == before


def test_osrm_http_error_is_unresolved(fake_osrm):
    base_url, handler = fake_osrm
    handler.mode = "error"
    try:
        result = _osrm(base_url).route(KAMPALA, ENTEBBE)
    finally:
        handler.mode = "ok"
    assert result.resolved is False


def test_osrm_empty_routes_is_unresolved(fake_osrm):
    base_url, handler = fake_osrm
    handler.mode = "malformed"
    try:
        result = _osrm(base_url).route(KAMPALA, ENTEBBE)
    finally:
        handler.mode = "ok"
    assert result.resolved is False


def test_osrm_disabled_never_touches_network(monkeypatch):
    from app.geo.providers.osrm import OSRMRouter
    called = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: called.append(1))
    router = OSRMRouter()
    assert router.is_available() is False
    assert router.route(KAMPALA, ENTEBBE).resolved is False
    assert called == []


def test_geoapify_normalizes_units_and_axis(fake_geoapify):
    base_url, _ = fake_geoapify
    result = _geoapify(base_url).route(KAMPALA, ENTEBBE)
    assert result.resolved is True
    assert result.provider == "geoapify"
    assert result.distance_m == pytest.approx(GEOAPIFY_DISTANCE_M)
    assert result.duration_s == pytest.approx(GEOAPIFY_DURATION_S)
    assert (result.geometry[0].latitude,
            result.geometry[0].longitude) == pytest.approx((0.3476, 32.5825))


@pytest.mark.parametrize("profile,mode", [
    ("auto", "drive"),
    ("motorcycle", "motorcycle"),
    ("pedestrian", "walk"),
    ("bicycle", "bicycle"),
])
def test_geoapify_profile_mode_mapping(fake_geoapify, profile, mode):
    base_url, handler = fake_geoapify
    handler.requests_seen = []
    result = _geoapify(base_url).route(KAMPALA, ENTEBBE, profile=profile)
    assert result.resolved is True
    parsed = urlparse(handler.requests_seen[-1])
    assert parsed.path == "/v1/routing"
    query = parse_qs(parsed.query)
    assert query["mode"] == [mode]
    assert query["waypoints"] == ["0.3476,32.5825|0.0515,32.4467"]
    assert "test-key" not in repr(result)


def test_geoapify_http_error_is_unresolved(fake_geoapify):
    base_url, handler = fake_geoapify
    handler.mode = "error"
    try:
        result = _geoapify(base_url).route(KAMPALA, ENTEBBE)
    finally:
        handler.mode = "ok"
    assert result.resolved is False
    assert result.provider == "geoapify"


def test_geoapify_without_key_never_touches_network(monkeypatch):
    from app.geo.providers.geoapify import GeoapifyConfig
    from app.geo.providers.geoapify_routing import GeoapifyRouter
    called = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: called.append(1))
    router = GeoapifyRouter(GeoapifyConfig(enabled=True, api_key=""))
    assert router.is_available() is False
    assert router.route(KAMPALA, ENTEBBE).resolved is False
    assert called == []


def _graphhopper(base_url, **overrides):
    from app.geo.providers.graphhopper import (GraphHopperConfig,
                                               GraphHopperRouter)
    kwargs = {"base_url": base_url, "api_key": "test-key", "enabled": True}
    kwargs.update(overrides)
    return GraphHopperRouter(GraphHopperConfig(**kwargs))


def _ors(base_url, **overrides):
    from app.geo.providers.ors import ORSConfig, ORSRouter
    kwargs = {"base_url": base_url, "api_key": "test-key", "enabled": True}
    kwargs.update(overrides)
    return ORSRouter(ORSConfig(**kwargs))


def test_graphhopper_normalizes_milliseconds_and_axis(fake_graphhopper):
    base_url, _ = fake_graphhopper
    result = _graphhopper(base_url).route(KAMPALA, ENTEBBE)
    assert result.resolved is True
    assert result.provider == "graphhopper"
    assert result.distance_m == pytest.approx(OSRM_DISTANCE_M)
    assert result.duration_s == pytest.approx(OSRM_DURATION_S)
    assert (result.geometry[0].latitude,
            result.geometry[0].longitude) == pytest.approx((0.3476, 32.5825))


def test_graphhopper_wire_uses_point_profile_and_key(fake_graphhopper):
    base_url, handler = fake_graphhopper
    handler.requests_seen = []
    _graphhopper(base_url).route(KAMPALA, ENTEBBE, profile="motorcycle")
    parsed = urlparse(handler.requests_seen[-1])
    query = parse_qs(parsed.query)
    assert parsed.path == "/route"
    assert query["point"] == ["0.3476,32.5825", "0.0515,32.4467"]
    assert query["profile"] == ["motorcycle"]
    assert query["points_encoded"] == ["false"]


def test_graphhopper_http_error_is_unresolved(fake_graphhopper):
    base_url, handler = fake_graphhopper
    handler.mode = "error"
    try:
        assert _graphhopper(base_url).route(KAMPALA, ENTEBBE).resolved is False
    finally:
        handler.mode = "ok"


def test_ors_normalizes_units_axis_and_auth(fake_ors):
    base_url, handler = fake_ors
    handler.requests_seen = []
    handler.bodies = []
    handler.auth = []
    result = _ors(base_url).route(KAMPALA, ENTEBBE)
    assert result.resolved is True
    assert result.provider == "ors"
    assert result.distance_m == pytest.approx(GEOAPIFY_DISTANCE_M)
    assert result.duration_s == pytest.approx(GEOAPIFY_DURATION_S)
    assert (result.geometry[0].latitude,
            result.geometry[0].longitude) == pytest.approx((0.3476, 32.5825))
    assert handler.requests_seen[-1] == (
        "/v2/directions/driving-car/geojson")
    assert handler.auth[-1] == "test-key"
    assert handler.bodies[-1]["coordinates"] == [
        [32.5825, 0.3476], [32.4467, 0.0515]]


@pytest.mark.parametrize("profile,path", [
    ("auto", "driving-car"),
    ("pedestrian", "foot-walking"),
    ("bicycle", "cycling-regular"),
])
def test_ors_profile_mapping(fake_ors, profile, path):
    base_url, handler = fake_ors
    handler.requests_seen = []
    assert _ors(base_url).route(KAMPALA, ENTEBBE,
                                profile=profile).resolved is True
    assert handler.requests_seen[-1] == f"/v2/directions/{path}/geojson"


def test_ors_motorcycle_is_truthful_miss(fake_ors):
    base_url, handler = fake_ors
    before = len(handler.requests_seen)
    result = _ors(base_url).route(KAMPALA, ENTEBBE, profile="motorcycle")
    assert result.resolved is False
    assert len(handler.requests_seen) == before


@pytest.mark.parametrize("factory,overrides", [
    (_graphhopper, {"enabled": False}),
    (_graphhopper, {"api_key": ""}),
    (_ors, {"enabled": False}),
    (_ors, {"api_key": ""}),
])
def test_optional_engine_not_configured_is_truthful_miss(factory, overrides):
    result = factory("http://127.0.0.1:1", **overrides).route(
        KAMPALA, ENTEBBE)
    assert result.resolved is False


class _StubRouter:
    def __init__(self, name, result=None, available=True, raises=None):
        self.name = name
        self._result = result
        self._available = available
        self._raises = raises
        self.calls = 0

    def is_available(self):
        return self._available

    def route(self, origin, destination, profile="auto"):
        self.calls += 1
        if self._raises:
            raise self._raises
        return self._result or RouteResult(
            distance_m=0.0, duration_s=0.0, provider=self.name,
            resolved=False)


def test_chain_falls_back_after_unresolved_primary():
    primary = _StubRouter("primary")
    secondary = _StubRouter(
        "secondary",
        RouteResult(distance_m=1000.0, duration_s=120.0,
                    provider="secondary", resolved=True))
    service = RoutingService(provider=primary, fallbacks=[secondary])
    result = service.route(KAMPALA, ENTEBBE)
    assert result.resolved is True
    assert result.provider == "secondary"
    assert primary.calls == 1
    assert secondary.calls == 1


def test_explicit_provider_does_not_leak_to_fallback():
    primary = _StubRouter(
        "primary",
        RouteResult(distance_m=1000.0, duration_s=120.0,
                    provider="primary", resolved=True))
    secondary = _StubRouter("secondary")
    service = RoutingService(provider=primary, fallbacks=[secondary])
    result = service.route(KAMPALA, ENTEBBE, provider="secondary")
    assert result.resolved is False
    assert result.provider == "secondary"
    assert primary.calls == 0
    assert secondary.calls == 1


def test_chain_failure_returns_labelled_straight_line():
    service = RoutingService(
        provider=_StubRouter("primary", raises=RuntimeError("boom")))
    result = service.route(KAMPALA, ENTEBBE)
    assert result.resolved is False
    assert result.provider == "haversine-fallback"
    assert result.distance_m > 0


def test_chain_never_swallows_validation_error():
    service = RoutingService(provider=_StubRouter("primary"))
    with pytest.raises(ValidationError):
        service.route(GeoPoint(91.0, 0.0), ENTEBBE)


def test_build_routing_service_explicit_osrm_chain():
    from app.geo.config import GeoConfig, RoutingConfig
    from app.geo.providers.geoapify import GeoapifyConfig
    from app.geo.providers.osrm import OSRMConfig
    from app.geo.providers.photon import PhotonConfig
    from app.geo.providers.tiles import TileProviderConfig
    from app.geo.providers.valhalla import ValhallaConfig
    from app.geo.services import build_routing_service
    config = GeoConfig(
        valhalla=ValhallaConfig(),
        photon=PhotonConfig(),
        tiles=TileProviderConfig(),
        geoapify=GeoapifyConfig(base_url="http://geoapify.test",
                                api_key="test-key", enabled=False),
        osrm=OSRMConfig(base_url="http://osrm.test", enabled=False),
        routing=RoutingConfig(provider="osrm",
                              fallbacks=("geoapify",), profile="motorcycle"),
    )
    service = build_routing_service(config)
    assert service.provider_name == "osrm"
    assert service.provider_names == ("osrm", "geoapify")
    assert service.profile == "motorcycle"


def test_build_routing_provider_force_enables_configured_adapter():
    from app.geo.config import GeoConfig
    from app.geo.providers.geoapify import GeoapifyConfig
    from app.geo.providers.google import GoogleMapsConfig
    from app.geo.providers.graphhopper import GraphHopperConfig
    from app.geo.providers.ors import ORSConfig
    from app.geo.providers.osrm import OSRMConfig
    from app.geo.providers.photon import PhotonConfig
    from app.geo.providers.tiles import TileProviderConfig
    from app.geo.providers.valhalla import ValhallaConfig
    from app.geo.services import build_routing_provider
    config = GeoConfig(
        valhalla=ValhallaConfig(),
        photon=PhotonConfig(),
        tiles=TileProviderConfig(),
        geoapify=GeoapifyConfig(base_url="http://geoapify.test",
                                api_key="test-key", enabled=False),
        osrm=OSRMConfig(base_url="http://osrm.test", enabled=False),
        graphhopper=GraphHopperConfig(base_url="http://graphhopper.test",
                                      api_key="test-key", enabled=False),
        ors=ORSConfig(base_url="http://ors.test", api_key="test-key",
                      enabled=False),
        google=GoogleMapsConfig(base_url="http://google.test",
                                api_key="test-key", enabled=False),
    )
    for name in ("osrm", "geoapify", "graphhopper", "ors", "google"):
        assert build_routing_provider(name, config, force=True) is not None
    assert build_routing_provider("valhalla", config, force=True) is None
    assert build_routing_provider("graphhopper", config) is None
    assert build_routing_provider("ors", config) is None
    assert build_routing_provider("google", config) is None
