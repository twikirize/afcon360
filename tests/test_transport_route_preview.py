"""RIDER-ROAD-ROUTE-PREVIEW-01 API contract tests."""

import math

import pytest

from app.geo.interfaces import GeoPoint, RouteResult
from app.transport.api import route_preview_routes


def _body():
    return {
        "pickup_latitude": 0.3476,
        "pickup_longitude": 32.5825,
        "dropoff_latitude": 0.0515,
        "dropoff_longitude": 32.4467,
    }


class _RoutingStub:
    provider_name = "valhalla"

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def route(self, origin, destination, profile="auto"):
        self.calls.append((origin, destination, profile))
        if self.error is not None:
            raise self.error
        return self.result


def test_route_preview_returns_provider_geometry_and_normalized_units(
        anonymous_client, monkeypatch):
    geometry = [
        GeoPoint(0.3476, 32.5825),
        GeoPoint(0.2000, 32.5100),
        GeoPoint(0.0515, 32.4467),
    ]
    service = _RoutingStub(RouteResult(
        distance_m=45352.0,
        duration_s=2734.163,
        geometry=geometry,
        provider="valhalla",
        resolved=True,
    ))
    monkeypatch.setattr(route_preview_routes, "get_routing_service",
                        lambda: service)

    response = anonymous_client.post(
        "/api/transport/route-preview", json=_body()
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store, max-age=0"
    vary_headers = {
        value.strip().lower()
        for value in response.headers.get("Vary", "").split(",")
    }
    assert "cookie" in vary_headers
    payload = response.get_json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["resolved"] is True
    assert data["distance_m"] == 45352.0
    assert data["duration_s"] == 2734.163
    assert data["provider"] == "valhalla"
    assert data["profile"] == "auto"
    assert data["geometry"] == [
        {"latitude": 0.3476, "longitude": 32.5825},
        {"latitude": 0.2, "longitude": 32.51},
        {"latitude": 0.0515, "longitude": 32.4467},
    ]
    assert len(service.calls) == 1
    origin, destination, profile = service.calls[0]
    assert origin == GeoPoint(0.3476, 32.5825)
    assert destination == GeoPoint(0.0515, 32.4467)
    assert profile == "auto"


def test_route_preview_unresolved_provider_has_no_measurements_or_geometry(
        anonymous_client, monkeypatch):
    service = _RoutingStub(RouteResult(
        distance_m=None,
        duration_s=None,
        geometry=[],
        provider="unresolved",
        resolved=False,
    ))
    monkeypatch.setattr(route_preview_routes, "get_routing_service",
                        lambda: service)

    response = anonymous_client.post(
        "/api/transport/route-preview", json=_body()
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data == {
        "resolved": False,
        "distance_m": None,
        "duration_s": None,
        "provider": "unresolved",
        "profile": "auto",
        "geometry": [],
    }


@pytest.mark.parametrize("field,value", [
    ("pickup_latitude", True),
    ("pickup_longitude", False),
    ("pickup_latitude", math.nan),
    ("dropoff_longitude", math.inf),
    ("pickup_latitude", 91),
    ("pickup_longitude", 181),
    ("dropoff_latitude", "not-a-number"),
    ("dropoff_longitude", -181),
    ("dropoff_latitude", ""),
])
def test_route_preview_rejects_invalid_raw_coordinates_before_provider_io(
        anonymous_client, monkeypatch, field, value):
    service = _RoutingStub(RouteResult(resolved=True))
    monkeypatch.setattr(route_preview_routes, "get_routing_service",
                        lambda: service)
    body = _body()
    body[field] = value

    response = anonymous_client.post(
        "/api/transport/route-preview", json=body
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "INVALID_ROUTE_INPUT"
    assert payload["field"] == field
    assert service.calls == []


@pytest.mark.parametrize("field", [
    "pickup_latitude",
    "pickup_longitude",
    "dropoff_latitude",
    "dropoff_longitude",
])
def test_route_preview_rejects_missing_coordinate_before_provider_io(
        anonymous_client, monkeypatch, field):
    service = _RoutingStub(RouteResult(resolved=True))
    monkeypatch.setattr(route_preview_routes, "get_routing_service",
                        lambda: service)
    body = _body()
    body.pop(field)

    response = anonymous_client.post(
        "/api/transport/route-preview", json=body
    )

    assert response.status_code == 400
    assert response.get_json()["field"] == field
    assert service.calls == []


def test_route_preview_provider_exception_is_truthful_unresolved_result(
        anonymous_client, monkeypatch):
    service = _RoutingStub(error=RuntimeError("upstream URL must not leak"))
    monkeypatch.setattr(route_preview_routes, "get_routing_service",
                        lambda: service)

    response = anonymous_client.post(
        "/api/transport/route-preview", json=_body()
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["resolved"] is False
    assert data["distance_m"] is None
    assert data["duration_s"] is None
    assert data["geometry"] == []
    assert "upstream URL" not in response.get_data(as_text=True)


@pytest.mark.parametrize("result", [
    RouteResult(
        distance_m=None, duration_s=100,
        geometry=[GeoPoint(0.3, 32.5)],
        provider="valhalla", resolved=True,
    ),
    RouteResult(
        distance_m=1000, duration_s=100,
        geometry=[],
        provider="valhalla", resolved=True,
    ),
    RouteResult(
        distance_m=1000, duration_s=100,
        geometry=[GeoPoint(91, 32.5)],
        provider="valhalla", resolved=True,
    ),
])
def test_route_preview_downgrades_malformed_resolved_provider_results(
        anonymous_client, monkeypatch, result):
    service = _RoutingStub(result)
    monkeypatch.setattr(route_preview_routes, "get_routing_service",
                        lambda: service)

    response = anonymous_client.post(
        "/api/transport/route-preview", json=_body()
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["resolved"] is False
    assert data["distance_m"] is None
    assert data["duration_s"] is None
    assert data["geometry"] == []
