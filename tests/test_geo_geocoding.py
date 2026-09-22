"""GEO geocoding/places — contract tests (geocoding node).

Proves the forward/reverse contract against a controlled localhost fake
Photon server (real HTTP round-trip through OUR adapter code). The fake
serves canned GeoJSON so request mapping, [lon,lat]→lat-first conversion,
normalization, and failure mapping are genuinely exercised. It is
explicitly NOT live Photon: no external traffic, no credentials.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from app.geo.interfaces import GeoPoint
from app.geo.services import GeocodingService
from app.utils.exceptions import ValidationError


KAMPALA = GeoPoint(0.3476, 32.5825)


def _feature(lon, lat, name, city="Kampala", country="Uganda"):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "osm_id": 12345, "osm_type": "N",
            "name": name, "city": city, "country": country,
        },
    }


FAKE_COLLECTION = {
    "type": "FeatureCollection",
    "features": [
        _feature(32.5825, 0.3476, "Nakasero Market"),
        _feature(32.5800, 0.3500, "Nakasero Hill"),
    ],
}


class _FakePhotonHandler(BaseHTTPRequestHandler):
    """Controlled stand-in. Records requests for order/param assertions."""
    calls = []
    mode = "ok"  # ok | empty | error | malformed | slow

    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        type(self).calls.append(
            (parsed.path, parse_qs(parsed.query)))
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
        elif self.mode == "slow":
            import time
            time.sleep(2.0)
            payload = json.dumps(FAKE_COLLECTION).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except Exception:
                pass  # client timed out and went away: expected
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
    yield (f"http://127.0.0.1:{server.server_port}",
           _FakePhotonHandler)
    server.shutdown()
    thread.join(timeout=5)


def _geocoder(base_url, **overrides):
    from app.geo.providers.photon import PhotonConfig, PhotonGeocoder
    kwargs = {"base_url": base_url, "enabled": True}
    kwargs.update(overrides)
    return PhotonGeocoder(PhotonConfig(**kwargs))


# --- forward geocoding ------------------------------------------------------------

def test_forward_returns_normalized_candidates(fake_photon):
    base_url, _ = fake_photon
    hits = _geocoder(base_url).geocode("Nakasero", limit=5)
    assert len(hits) == 2
    first, second = hits
    assert first.resolved is True
    assert first.provider == "photon"
    # GeoJSON [lon, lat] converted back to latitude-first GeoPoint order.
    assert (first.latitude, first.longitude) == pytest.approx(
        (0.3476, 32.5825))
    assert (second.latitude, second.longitude) == pytest.approx(
        (0.3500, 32.5800))
    assert "Nakasero Market" in first.display_name
    assert first.raw.get("osm_id") == 12345


def test_forward_request_carries_query_and_limit(fake_photon):
    base_url, handler = fake_photon
    handler.calls = []
    _geocoder(base_url).geocode("Nakasero Market", limit=3)
    assert handler.calls, "adapter must GET the provider"
    path, params = handler.calls[-1]
    assert path == "/api"
    assert params.get("q") == ["Nakasero Market"]
    assert params.get("limit") == ["3"]


def test_forward_empty_collection_returns_empty_list(fake_photon):
    base_url, handler = fake_photon
    handler.mode = "empty"
    try:
        assert _geocoder(base_url).geocode("Nowhere XYZ") == []
    finally:
        handler.mode = "ok"


@pytest.mark.parametrize("bad_query", ["", "   ", None, 123])
def test_forward_invalid_query_raises_before_io(fake_photon, bad_query):
    base_url, handler = fake_photon
    before = len(handler.calls)
    with pytest.raises(ValidationError):
        _geocoder(base_url).geocode(bad_query)
    assert len(handler.calls) == before  # never touches the network


def test_forward_malformed_features_skipped_not_fabricated(
        custom_collection_server):
    """A collection mixing one malformed feature with one valid feature
    yields exactly the valid hit: malformed entries are skipped, never
    fabricated and never fatal to the whole response."""
    base_url, handler = custom_collection_server
    handler.payload = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature"},  # no geometry/properties
            _feature(32.5825, 0.3476, "Nakasero Market"),
        ],
    }
    hits = _geocoder(base_url).geocode("Nakasero")
    assert len(hits) == 1
    assert hits[0].resolved is True
    assert "Nakasero Market" in hits[0].display_name


class _PayloadHandler(_FakePhotonHandler):
    """Serves whatever collection the test assigns to `payload`."""
    payload = {}

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


# --- reverse geocoding ---------------------------------------------------------------

def test_reverse_returns_normalized_address(fake_photon):
    base_url, _ = fake_photon
    result = _geocoder(base_url).reverse(KAMPALA)
    assert result.resolved is True
    assert result.provider == "photon"
    assert (result.latitude, result.longitude) == pytest.approx(
        (0.3476, 32.5825))
    assert "Nakasero Market" in result.display_name


def test_reverse_request_carries_lat_lon_order(fake_photon):
    base_url, handler = fake_photon
    handler.calls = []
    _geocoder(base_url).reverse(KAMPALA)
    assert handler.calls, "adapter must GET the provider"
    path, params = handler.calls[-1]
    assert path == "/reverse"
    # Reversal-detecting: lat param must hold the latitude, not longitude.
    assert params.get("lat") == ["0.3476"]
    assert params.get("lon") == ["32.5825"]


def test_reverse_empty_returns_unresolved(fake_photon):
    base_url, handler = fake_photon
    handler.mode = "empty"
    try:
        result = _geocoder(base_url).reverse(KAMPALA)
    finally:
        handler.mode = "ok"
    assert result.resolved is False


@pytest.mark.parametrize("bad", [
    GeoPoint(91.0, 0.0),
    GeoPoint(0.0, 181.0),
    GeoPoint(float("nan"), 0.0),
])
def test_reverse_invalid_point_raises_before_io(fake_photon, bad):
    base_url, handler = fake_photon
    before = len(handler.calls)
    with pytest.raises(ValidationError):
        _geocoder(base_url).reverse(bad)
    assert len(handler.calls) == before


# --- failure truthfulness -----------------------------------------------------------------

def test_disabled_adapter_never_touches_network(monkeypatch):
    from app.geo.providers.photon import PhotonGeocoder
    posted = []
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: posted.append((a, k)))
    geocoder = PhotonGeocoder()  # disabled by default
    assert geocoder.is_available() is False
    assert geocoder.geocode("Kampala") == []
    assert geocoder.reverse(KAMPALA).resolved is False
    assert posted == []


def test_http_error_returns_empty_and_unresolved(fake_photon):
    base_url, handler = fake_photon
    handler.mode = "error"
    try:
        assert _geocoder(base_url).geocode("Kampala") == []
        assert _geocoder(base_url).reverse(KAMPALA).resolved is False
    finally:
        handler.mode = "ok"


def test_malformed_response_returns_empty_and_unresolved(fake_photon):
    base_url, handler = fake_photon
    handler.mode = "malformed"
    try:
        assert _geocoder(base_url).geocode("Kampala") == []
        assert _geocoder(base_url).reverse(KAMPALA).resolved is False
    finally:
        handler.mode = "ok"


def test_timeout_returns_empty_and_unresolved(fake_photon):
    base_url, handler = fake_photon
    handler.mode = "slow"
    try:
        geocoder = _geocoder(base_url, timeout_s=0.2)
        assert geocoder.geocode("Kampala") == []
        assert geocoder.reverse(KAMPALA).resolved is False
    finally:
        handler.mode = "ok"


# --- wiring factory ----------------------------------------------------------------------------

def test_build_geocoding_service_disabled_keeps_miss():
    from app.geo.config import GeoConfig
    from app.geo.providers.photon import PhotonConfig
    from app.geo.providers.tiles import TileProviderConfig
    from app.geo.providers.valhalla import ValhallaConfig
    from app.geo.services import build_geocoding_service
    config = GeoConfig(valhalla=ValhallaConfig(),
                       photon=PhotonConfig(),
                       tiles=TileProviderConfig())
    service = build_geocoding_service(config)
    assert service.provider_name == "unresolved"
    assert service.geocode("Kampala") == []
    assert service.reverse(KAMPALA).resolved is False


def test_build_geocoding_service_enabled_wires_adapter_without_io(
        fake_photon):
    from app.geo.config import GeoConfig
    from app.geo.providers.photon import PhotonConfig
    from app.geo.providers.tiles import TileProviderConfig
    from app.geo.providers.valhalla import ValhallaConfig
    from app.geo.services import build_geocoding_service
    from app.geo.services import GeocodingService
    base_url, handler = fake_photon
    before = len(handler.calls)
    config = GeoConfig(
        valhalla=ValhallaConfig(),
        photon=PhotonConfig(base_url=base_url, enabled=True),
        tiles=TileProviderConfig())
    service = build_geocoding_service(config)
    assert service.provider_name == "photon"
    assert len(handler.calls) == before  # wiring performs no I/O
    assert isinstance(service, GeocodingService)
