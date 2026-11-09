from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


def _authenticated_driver(monkeypatch):
    from app.auth import mobile_api

    user = SimpleNamespace(id=451, public_id="driver-public-451")
    profile = SimpleNamespace(
        id=902,
        user_id=user.id,
        is_deleted=False,
        last_location={"latitude": 0.3136, "longitude": 32.5811},
        location_updated_at=datetime.now(timezone.utc),
    )
    calls = {}

    def require_context(expected_client=None):
        calls["expected_client"] = expected_client
        return {
            "user": user,
            "record": {"client": "driver"},
        }, None

    monkeypatch.setattr(mobile_api, "require_mobile_context", require_context)
    monkeypatch.setattr(mobile_api, "_current_driver", lambda: (profile, None, 200))
    return profile, calls


def test_mobile_driver_demand_route_requires_driver_bearer(client):
    response = client.get("/api/mobile/v1/driver/demand/cells")

    assert response.status_code == 401
    assert response.get_json()["code"] == "mobile_auth_required"


def test_mobile_driver_demand_route_is_driver_scoped_and_private(
    client, monkeypatch
):
    from app.transport.services import driver_demand_service

    profile, calls = _authenticated_driver(monkeypatch)
    captured = {}

    payload = {
        "success": True,
        "state": "available",
        "cells": [
            {
                "center": {"latitude": 0.31, "longitude": 32.58},
                "request_count": 3,
            }
        ],
        "window": {
            "since": "2026-11-09T00:00:00+00:00",
            "until": "2026-11-10T00:00:00+00:00",
        },
        "computed_at": "2026-11-10T00:00:00+00:00",
        "skipped_invalid": 0,
        "truncated": False,
    }

    def fake_demand(resolved_profile):
        captured["profile"] = resolved_profile
        return payload

    monkeypatch.setattr(
        driver_demand_service,
        "get_driver_demand_cells",
        fake_demand,
    )

    response = client.get(
        "/api/mobile/v1/driver/demand/cells",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200
    assert calls["expected_client"] == "driver"
    assert captured["profile"] is profile
    assert response.get_json() == payload
    assert response.headers["Cache-Control"] == "private, no-store, max-age=0"
    assert "authorization" in {
        value.strip().lower() for value in response.headers["Vary"].split(",")
    }

    body = response.get_data(as_text=True).lower()
    for forbidden in (
        "booking_reference",
        "booking_id",
        "driver_id",
        "fare",
        "pickup_location",
        "longitude",
        "latitude",
        "passenger",
    ):
        assert forbidden not in body


def test_mobile_driver_demand_route_is_registered_for_get(app):
    routes = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/mobile/v1/driver/demand/cells"
    ]
    assert len(routes) == 1
    assert "GET" in routes[0].methods


def test_driver_demand_service_hides_missing_stale_and_future_locations(
    monkeypatch,
):
    from app.transport.services import driver_demand_service

    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    missing = SimpleNamespace(
        is_deleted=False,
        last_location=None,
        location_updated_at=None,
    )
    assert driver_demand_service.get_driver_demand_cells(
        missing, now=now
    )["state"] == "location_unavailable"

    stale = SimpleNamespace(
        is_deleted=False,
        last_location={"latitude": 0.3136, "longitude": 32.5811},
        location_updated_at=now - timedelta(minutes=6),
    )
    assert driver_demand_service.get_driver_demand_cells(
        stale, now=now
    )["state"] == "location_unavailable"

    future = SimpleNamespace(
        is_deleted=False,
        last_location={"latitude": 0.3136, "longitude": 32.5811},
        location_updated_at=now + timedelta(minutes=1),
    )
    assert driver_demand_service.get_driver_demand_cells(
        future, now=now
    )["state"] == "location_unavailable"


def test_driver_demand_service_filters_before_aggregation_and_applies_minimum(
    monkeypatch,
):
    from app.transport.services import driver_demand_service

    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    profile = SimpleNamespace(
        is_deleted=False,
        last_location={"latitude": 0.3136, "longitude": 32.5811},
        location_updated_at=now,
    )
    monkeypatch.setattr(
        driver_demand_service,
        "booking_request_points",
        lambda since, until: (
            [
                (0.3136, 32.5811, None),
                (0.3140, 32.5815, None),
                (0.3150, 32.5820, None),
                (0.90, 32.58, None),   # Outside the 25 km local radius.
                (100.0, 32.58, None),  # Invalid point; skipped.
            ],
            0,
        ),
    )

    result = driver_demand_service.get_driver_demand_cells(profile, now=now)

    assert result["success"] is True
    assert result["state"] == "available"
    assert result["cells"] == [
        {
            "center": {"latitude": 0.31, "longitude": 32.58},
            "request_count": 3,
        }
    ]
    assert result["skipped_invalid"] == 1
    assert result["window"]["since"] == (
        now - timedelta(hours=24)
    ).isoformat()


def test_driver_demand_service_returns_no_recent_demand_below_cell_threshold(
    monkeypatch,
):
    from app.transport.services import driver_demand_service

    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    profile = SimpleNamespace(
        is_deleted=False,
        last_location={"latitude": 0.3136, "longitude": 32.5811},
        location_updated_at=now,
    )
    monkeypatch.setattr(
        driver_demand_service,
        "booking_request_points",
        lambda since, until: (
            [
                (0.3136, 32.5811, None),
                (0.3140, 32.5815, None),
            ],
            0,
        ),
    )

    result = driver_demand_service.get_driver_demand_cells(profile, now=now)

    assert result["state"] == "no_recent_demand"
    assert result["cells"] == []
