"""GEO Geoapify adapter + provider chain — contract tests.

Proves against controlled localhost fakes (real HTTP through OUR adapter
code; never live Geoapify, no credentials):

  * Geoapify forward/reverse normalization (geojson FeatureCollection,
    [lon,lat] -> lat-first) into the existing GeocodeResult;
  * request shape (path, text/limit/format/lang params, identifying UA);
  * explicit failure classification: timeout / network / non-2xx /
    unusable shape raise ProviderFailure (fallback trigger); a VALID
    response with zero useful candidates returns [] (honest no-result);
  * the API key never appears in logs, results, raw, or health;
  * the GeocodingService chain policy: Geoapify failure -> Photon (ROLE A);
    Geoapify useful -> no Photon call; Geoapify valid-empty -> NO fallback;
    weak single hit -> conditional Photon supplement (ROLE B); double
    failure -> unresolved;
  * a Geoapify candidate flows through the existing echo seam into the
    canonical 13-key snapshot (source=search, forward_geocode,
    authority=geoapify).
"""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from app.geo.interfaces import GeoPoint
from app.geo.providers.base import ProviderFailure
from app.geo.services import GeocodingService, geoapify_needs_secondary
from app.utils.exceptions import ValidationError

KAMPALA = GeoPoint(0.3476, 32.5825)
API_KEY = "test-key-not-a-secret"


def _feature(lon, lat, formatted, name="Kampala",
             match_type="full_match", confidence=1.0):
    return {
        "type": "Feature",
        "properties": {
            "datasource": {
                "sourcename": "openstreetmap",
                "attribution": "© OpenStreetMap contributors",
                "license": "Open Database License",
                "url": "https://www.openstreetmap.org/copyright",
            },
            "country": "Uganda",
            "country_code": "ug",
            "state": "Central Region",
            "city": "Kampala",
            "lon": lon,
            "lat": lat,
            "formatted": formatted,
            "address_line1": name,
            "address_line2": "Kampala, Central Region, Uganda",
            "result_type": "locality",
            "rank": {"confidence": confidence,
                     "match_type": match_type},
            "place_id": "51ab791e4a0f7e5ec059b7c8a1d2f3a0147f00101f9011a2b0000000000c00208",
            "name": name,
        },
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "bbox": [lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01],
    }


FAKE_COLLECTION = {
    "type": "FeatureCollection",
    "features": [
        _feature(32.5813539, 0.3177137, "Kampala, Central Region, Uganda"),
        _feature(32.5877299, 0.3365912, "Acacia Mall, Kampala, Uganda",
                 name="Acacia Mall"),
    ],
}


class _FakeGeoapifyHandler(BaseHTTPRequestHandler):
    """Controlled Geoapify stand-in. Records requests incl. headers."""
    calls = []
    mode = "ok"  # ok | empty | error | unauthorized | ratelimited | malformed | slow | weak

    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        type(self).calls.append(
            (parsed.path, parse_qs(parsed.query),
             {"user-agent": self.headers.get("User-Agent")}))
        if self.mode == "error":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")
        elif self.mode == "unauthorized":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"invalid key"}')
        elif self.mode == "ratelimited":
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b'{"error":"rate limit"}')
        elif self.mode == "malformed":
            payload = json.dumps({"results": []}).encode()
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
                pass  # client timed out: expected
        elif self.mode == "empty":
            payload = json.dumps(
                {"type": "FeatureCollection", "features": []}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.mode == "weak":
            payload = json.dumps({
                "type": "FeatureCollection",
                "features": [_feature(
                    32.5813539, 0.3177137, "Kampala, Central Region, Uganda",
                    match_type="inner_match", confidence=0.4)],
            }).encode()
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
def fake_geoapify():
    _FakeGeoapifyHandler.calls = []
    _FakeGeoapifyHandler.mode = "ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeGeoapifyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield (f"http://127.0.0.1:{server.server_port}", _FakeGeoapifyHandler)
    server.shutdown()
    thread.join(timeout=5)


def _geocoder(base_url, **overrides):
    from app.geo.providers.geoapify import GeoapifyConfig, GeoapifyGeocoder
    kwargs = {"base_url": base_url, "api_key": API_KEY, "enabled": True}
    kwargs.update(overrides)
    return GeoapifyGeocoder(GeoapifyConfig(**kwargs))


# --- forward normalization ---------------------------------------------------

def test_forward_returns_normalized_candidates(fake_geoapify):
    base_url, _ = fake_geoapify
    hits = _geocoder(base_url).geocode("Kampala", limit=5)
    assert len(hits) == 2
    first = hits[0]
    assert first.resolved is True
    assert first.provider == "geoapify"
    # GeoJSON [lon, lat] converted back to latitude-first order.
    assert (first.latitude, first.longitude) == pytest.approx(
        (0.3177137, 32.5813539))
    assert first.display_name == "Kampala, Central Region, Uganda"
    assert set(first.raw) == {"geoapify_quality"}
    quality = first.raw["geoapify_quality"]
    assert quality["match_type"] == "full_match"
    assert quality["confidence"] == pytest.approx(1.0)


def test_forward_request_shape(fake_geoapify):
    base_url, handler = fake_geoapify
    handler.calls = []
    _geocoder(base_url).geocode("Kampala Serena", limit=3)
    assert handler.calls, "adapter must GET the provider"
    path, params, headers = handler.calls[-1]
    assert path == "/v1/geocode/search"
    assert params.get("text") == ["Kampala Serena"]
    assert params.get("limit") == ["3"]
    assert params.get("format") == ["geojson"]
    assert params.get("lang") == ["en"]
    assert params.get("apiKey") == [API_KEY]
    ua = headers["user-agent"] or ""
    assert "python-requests" not in ua
    assert ua.strip() != ""


def test_forward_valid_empty_returns_empty_list(fake_geoapify):
    base_url, handler = fake_geoapify
    handler.mode = "empty"
    try:
        assert _geocoder(base_url).geocode("Nowhere XYZ") == []
    finally:
        handler.mode = "ok"


@pytest.mark.parametrize("bad_query", ["", "   ", None, 123])
def test_forward_invalid_query_raises_before_io(fake_geoapify, bad_query):
    base_url, handler = fake_geoapify
    before = len(handler.calls)
    with pytest.raises(ValidationError):
        _geocoder(base_url).geocode(bad_query)
    assert len(handler.calls) == before


def test_forward_malformed_shape_raises_provider_failure(fake_geoapify):
    """A 200 without a list ``features`` is an operational failure (the
    service must fall back), never a silent empty."""
    base_url, handler = fake_geoapify
    handler.mode = "malformed"
    try:
        with pytest.raises(ProviderFailure):
            _geocoder(base_url).geocode("Kampala")
    finally:
        handler.mode = "ok"


# --- failure classification --------------------------------------------------

@pytest.mark.parametrize("mode", ["error", "unauthorized", "ratelimited"])
def test_forward_http_failures_raise_provider_failure(fake_geoapify, mode):
    base_url, handler = fake_geoapify
    handler.mode = mode
    try:
        with pytest.raises(ProviderFailure):
            _geocoder(base_url).geocode("Kampala")
        assert _geocoder(base_url).reverse(KAMPALA).resolved is False
    finally:
        handler.mode = "ok"


def test_forward_timeout_raises_provider_failure(fake_geoapify):
    base_url, handler = fake_geoapify
    handler.mode = "slow"
    try:
        geocoder = _geocoder(base_url, timeout_s=0.2)
        with pytest.raises(ProviderFailure):
            geocoder.geocode("Kampala")
        assert geocoder.reverse(KAMPALA).resolved is False
    finally:
        handler.mode = "ok"


def test_forward_network_failure_raises_provider_failure():
    from app.geo.providers.geoapify import GeoapifyConfig, GeoapifyGeocoder
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    dead_port = sock.getsockname()[1]
    sock.close()
    geocoder = GeoapifyGeocoder(GeoapifyConfig(
        base_url=f"http://127.0.0.1:{dead_port}", api_key=API_KEY,
        enabled=True))
    with pytest.raises(ProviderFailure):
        geocoder.geocode("Kampala")
    assert geocoder.reverse(KAMPALA).resolved is False


def test_disabled_adapter_never_touches_network(monkeypatch):
    from app.geo.providers.geoapify import GeoapifyGeocoder
    posted = []
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: posted.append((a, k)))
    geocoder = GeoapifyGeocoder()  # disabled, no key
    assert geocoder.is_available() is False
    assert geocoder.geocode("Kampala") == []
    assert geocoder.reverse(KAMPALA).resolved is False
    assert posted == []


def test_keyless_but_enabled_adapter_never_touches_network(monkeypatch):
    from app.geo.providers.geoapify import GeoapifyConfig, GeoapifyGeocoder
    posted = []
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: posted.append((a, k)))
    geocoder = GeoapifyGeocoder(GeoapifyConfig(
        base_url="http://127.0.0.1:1", enabled=True))  # no api_key
    assert geocoder.is_available() is False
    assert geocoder.geocode("Kampala") == []
    assert posted == []


# --- reverse -----------------------------------------------------------------

def test_reverse_returns_first_result(fake_geoapify):
    base_url, _ = fake_geoapify
    result = _geocoder(base_url).reverse(KAMPALA)
    assert result.resolved is True
    assert result.provider == "geoapify"
    assert (result.latitude, result.longitude) == pytest.approx(
        (0.3177137, 32.5813539))


def test_reverse_empty_returns_unresolved(fake_geoapify):
    base_url, handler = fake_geoapify
    handler.mode = "empty"
    try:
        assert _geocoder(base_url).reverse(KAMPALA).resolved is False
    finally:
        handler.mode = "ok"


@pytest.mark.parametrize("bad", [
    GeoPoint(91.0, 0.0),
    GeoPoint(0.0, 181.0),
    GeoPoint(float("nan"), 0.0),
])
def test_reverse_invalid_point_raises_before_io(fake_geoapify, bad):
    base_url, handler = fake_geoapify
    before = len(handler.calls)
    with pytest.raises(ValidationError):
        _geocoder(base_url).reverse(bad)
    assert len(handler.calls) == before


# --- secret hygiene ----------------------------------------------------------

def test_api_key_never_in_logs(fake_geoapify, caplog):
    import logging
    base_url, handler = fake_geoapify
    handler.mode = "error"
    try:
        with caplog.at_level(logging.WARNING,
                             logger="app.geo.providers.geoapify"):
            with pytest.raises(ProviderFailure):
                _geocoder(base_url).geocode("Kampala")
            _geocoder(base_url).reverse(KAMPALA)
    finally:
        handler.mode = "ok"
    assert API_KEY not in caplog.text


def test_api_key_never_in_results(fake_geoapify):
    base_url, _ = fake_geoapify
    hits = _geocoder(base_url).geocode("Kampala")
    blob = json.dumps([{"lat": h.latitude, "lon": h.longitude,
                        "name": h.display_name, "raw": h.raw,
                        "provider": h.provider} for h in hits])
    assert API_KEY not in blob


# --- chain policy ------------------------------------------------------------

def test_chain_geoapify_first_no_double_query(fake_geoapify):
    from app.geo.providers.photon import PhotonConfig, PhotonGeocoder
    geo_url, _ = fake_geoapify
    photon_calls = []
    photon = PhotonGeocoder(PhotonConfig(base_url="http://127.0.0.1:1",
                                         enabled=True))
    orig = photon.geocode

    def _spy(query, limit=5):
        photon_calls.append(query)
        return orig(query, limit=limit)
    photon.geocode = _spy
    service = GeocodingService(provider=_geocoder(geo_url),
                               fallbacks=[photon])
    hits = service.geocode("Kampala")
    assert hits and all(h.provider == "geoapify" for h in hits)
    assert photon_calls == []  # useful candidates: no fallback call


def test_chain_valid_empty_does_not_fall_back(fake_geoapify):
    """Policy C: valid success with zero useful candidates is an honest
    no-result — Photon must NOT be queried."""
    from app.geo.providers.photon import PhotonConfig, PhotonGeocoder
    geo_url, handler = fake_geoapify
    handler.mode = "empty"
    photon_calls = []
    photon = PhotonGeocoder(PhotonConfig(base_url="http://127.0.0.1:1",
                                         enabled=True))

    def _spy(query, limit=5):
        photon_calls.append(query)
        return []
    photon.geocode = _spy
    try:
        service = GeocodingService(provider=_geocoder(geo_url),
                                   fallbacks=[photon])
        assert service.geocode("Nowhere XYZ") == []
    finally:
        handler.mode = "ok"
    assert photon_calls == []


def test_chain_falls_back_on_operational_failure(fake_geoapify):
    """Policy A: timeout/network/5xx/429/401/unusable shape -> Photon."""
    from app.geo.interfaces import GeocodeResult
    from app.geo.providers.photon import PhotonConfig, PhotonGeocoder
    geo_url, handler = fake_geoapify
    handler.mode = "error"
    photon_hits = []
    photon = PhotonGeocoder(PhotonConfig(base_url="http://127.0.0.1:1",
                                         enabled=True))

    def _fake(query, limit=5):
        photon_hits.append(query)
        return [GeocodeResult(latitude=0.3, longitude=32.5,
                              display_name="Fallback Place",
                              provider="photon", resolved=True)]
    photon.geocode = _fake
    try:
        service = GeocodingService(provider=_geocoder(geo_url),
                                   fallbacks=[photon])
        hits = service.geocode("Kampala")
    finally:
        handler.mode = "ok"
    assert photon_hits == ["Kampala"]
    assert hits and hits[0].provider == "photon"


def test_chain_weak_single_hit_gets_photon_supplement(fake_geoapify):
    """Policy D: one weak Geoapify hit -> Photon appended after it."""
    from app.geo.interfaces import GeocodeResult
    from app.geo.providers.photon import PhotonConfig, PhotonGeocoder
    geo_url, handler = fake_geoapify
    handler.mode = "weak"
    photon = PhotonGeocoder(PhotonConfig(base_url="http://127.0.0.1:1",
                                         enabled=True))

    def _fake(query, limit=5):
        return [GeocodeResult(latitude=0.35, longitude=32.58,
                              display_name="Photon Second Opinion",
                              provider="photon", resolved=True)]
    photon.geocode = _fake
    try:
        service = GeocodingService(provider=_geocoder(geo_url),
                                   fallbacks=[photon])
        hits = service.geocode("Kampala")
    finally:
        handler.mode = "ok"
    assert [h.provider for h in hits] == ["geoapify", "photon"]


def test_chain_strong_hits_get_no_supplement(fake_geoapify):
    from app.geo.providers.photon import PhotonConfig, PhotonGeocoder
    geo_url, _ = fake_geoapify
    photon_calls = []
    photon = PhotonGeocoder(PhotonConfig(base_url="http://127.0.0.1:1",
                                         enabled=True))

    def _spy(query, limit=5):
        photon_calls.append(query)
        return []
    photon.geocode = _spy
    service = GeocodingService(provider=_geocoder(geo_url),
                               fallbacks=[photon])
    hits = service.geocode("Kampala")
    assert len(hits) == 2
    assert photon_calls == []


def test_weak_policy_unit_cases():
    from app.geo.interfaces import GeocodeResult

    def _hit(quality, n=1):
        return [GeocodeResult(latitude=0.3, longitude=32.5,
                              display_name="X", provider="geoapify",
                              raw={"geoapify_quality": quality},
                              resolved=True) for _ in range(n)]

    assert geoapify_needs_secondary(
        _hit({"match_type": "inner_match", "confidence": 0.4})) is True
    assert geoapify_needs_secondary(
        _hit({"match_type": "full_match", "confidence": 0.2})) is True
    assert geoapify_needs_secondary(
        _hit({"match_type": "full_match", "confidence": 1})) is False
    assert geoapify_needs_secondary(
        _hit({"match_type": None, "confidence": None})) is False
    assert geoapify_needs_secondary(
        _hit({"match_type": "full_match", "confidence": 1}, n=2)) is False
    assert geoapify_needs_secondary([]) is False
    assert geoapify_needs_secondary(
        [GeocodeResult(latitude=0.3, longitude=32.5,
                       display_name="P", provider="photon",
                       resolved=True)]) is False


def test_chain_double_failure_is_unresolved():
    from app.geo.providers.geoapify import GeoapifyConfig, GeoapifyGeocoder
    from app.geo.providers.photon import PhotonConfig, PhotonGeocoder
    service = GeocodingService(
        provider=GeoapifyGeocoder(GeoapifyConfig(
            base_url="http://127.0.0.1:1", api_key="x", enabled=True)),
        fallbacks=[PhotonGeocoder(PhotonConfig(
            base_url="http://127.0.0.1:1", enabled=True))])
    assert service.geocode("Kampala") == []
    assert service.reverse(KAMPALA).resolved is False


def test_build_service_wires_geoapify_first(fake_geoapify):
    from app.geo.config import GeoConfig
    from app.geo.providers.geoapify import GeoapifyConfig
    from app.geo.providers.photon import PhotonConfig
    from app.geo.providers.tiles import TileProviderConfig
    from app.geo.providers.valhalla import ValhallaConfig
    from app.geo.services import build_geocoding_service
    geo_url, handler = fake_geoapify
    before = len(handler.calls)
    config = GeoConfig(
        valhalla=ValhallaConfig(),
        photon=PhotonConfig(base_url="http://127.0.0.1:1", enabled=True),
        geoapify=GeoapifyConfig(base_url=geo_url, api_key=API_KEY,
                                enabled=True),
        tiles=TileProviderConfig())
    service = build_geocoding_service(config)
    assert service.provider_name == "geoapify"
    assert len(handler.calls) == before  # wiring performs no I/O
    hits = service.geocode("Kampala")
    assert hits and hits[0].provider == "geoapify"


def test_build_service_without_geoapify_keeps_photon():
    from app.geo.config import GeoConfig
    from app.geo.providers.photon import PhotonConfig
    from app.geo.providers.tiles import TileProviderConfig
    from app.geo.providers.valhalla import ValhallaConfig
    from app.geo.services import build_geocoding_service
    config = GeoConfig(
        valhalla=ValhallaConfig(),
        photon=PhotonConfig(base_url="http://127.0.0.1:1", enabled=True),
        tiles=TileProviderConfig())
    service = build_geocoding_service(config)
    assert service.provider_name == "photon"


# --- reverse presentability ----------------------------------------------------

def _rev_feature(**over):
    props = {
        "formatted": "Sheraton Kampala Hotel, Kampala, Uganda",
        "name": "Sheraton Kampala Hotel",
        "city": "Kampala",
        "country": "Uganda",
        "result_type": "amenity",
        "rank": {"confidence": 1, "match_type": "full_match"},
    }
    props.update(over)
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [32.58207, 0.31693]},
    }


def _presentable(feature):
    from app.geo.providers.geoapify import _feature_to_result
    from app.geo.services import reverse_identity_presentable
    result = _feature_to_result(feature, "geoapify")
    assert result is not None and result.resolved is True
    return reverse_identity_presentable(result)


def test_presentable_named_place():
    assert _presentable(_rev_feature()) is True


def test_not_presentable_unknown_type():
    assert _presentable(_rev_feature(result_type="unknown")) is False


def test_not_presentable_empty_formatted():
    assert _presentable(_rev_feature(formatted="  ")) is False


def test_not_presentable_water_body():
    assert _presentable(_rev_feature(
        formatted="Earth", name="Earth", result_type="amenity",
        ocean="South Atlantic Ocean")) is False


def test_not_presentable_unresolved_or_blank():
    from app.geo.interfaces import GeocodeResult
    from app.geo.services import reverse_identity_presentable
    assert reverse_identity_presentable(
        GeocodeResult(provider="geoapify", resolved=False)) is False
    assert reverse_identity_presentable(
        GeocodeResult(latitude=0.0, longitude=0.0, display_name="   ",
                      provider="geoapify", resolved=True)) is False


def test_photon_result_presentable_on_name_only():
    """Providers without type/water signals: non-empty identity suffices
    (documented limitation: water-class features cannot be filtered)."""
    from app.geo.interfaces import GeocodeResult
    from app.geo.services import reverse_identity_presentable
    assert reverse_identity_presentable(
        GeocodeResult(latitude=0.3, longitude=32.5,
                      display_name="Nakasero Market, Kampala, Uganda",
                      raw={"name": "Nakasero Market"},
                      provider="photon", resolved=True)) is True


def test_reverse_quality_signals_stay_out_of_canonical():
    """geoapify_quality never reaches the 13-key snapshot (no datum pair
    for Geoapify exists in the echo contract)."""
    from app.geo.providers.geoapify import _feature_to_result
    from app.geo.services import geocode_result_from_candidate
    result = _feature_to_result(_rev_feature(), "geoapify")
    assert result is not None and result.resolved is True
    assert set(result.raw) == {"geoapify_quality"}
    candidate = {"label": result.display_name, "latitude": result.latitude,
                 "longitude": result.longitude, "provider": "geoapify"}
    rebuilt = geocode_result_from_candidate(candidate)
    assert rebuilt.raw == {}


# --- canonical -----------------------------------------------------------------

def test_geoapify_candidate_builds_canonical_search_snapshot():
    from app.geo.services import geocode_result_from_candidate
    from app.transport.services.location_snapshot import (
        build_canonical_location_snapshot)
    candidate = {
        "label": "Kampala, Central Region, Uganda",
        "latitude": 0.3177137,
        "longitude": 32.5813539,
        "provider": "geoapify",
    }
    result = geocode_result_from_candidate(candidate)
    assert result.resolved is True
    assert result.provider == "geoapify"
    snapshot = build_canonical_location_snapshot(
        location_payload={"latitude": 0.3177137, "longitude": 32.5813539},
        geocode_result=result,
        explicit_address=candidate["label"],
        source="search",
        resolution_method="forward_geocode",
    )
    assert sorted(snapshot.keys()) == sorted([
        "latitude", "longitude", "source", "resolution_method",
        "provenance", "label", "display_name", "identity_status",
        "area", "accuracy_m", "confidence", "observed_at", "resolved_at",
    ])
    assert snapshot["source"] == "search"
    assert snapshot["resolution_method"] == "forward_geocode"
    assert snapshot["provenance"] == {"authority": "geoapify",
                                      "reference": None}
    assert snapshot["label"] == "Kampala, Central Region, Uganda"
    assert snapshot["display_name"] == "Kampala, Central Region, Uganda"
    assert snapshot["identity_status"] == "unverified"
    assert "geoapify_" not in json.dumps(snapshot)
