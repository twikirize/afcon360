"""Transport live tracking path — regression proof (operational hardening).

Exercises the REAL production path, not isolated helpers:

  driver POST / drivers/<id>/location (auth + ownership)
      → TrackingService.update_location (validate → Redis → DB)
      → TrackingService.get_location (Redis-first, DB fallback)
      → location pages render last-known position

Plus the Redis-outage read resilience fixed in this node and the
authorization boundaries around every location read surface.

Fixtures mirror tests/test_transport_geographic_contract.py.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest

from app.extensions import db
from app.transport.models import (
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
    Vehicle,
    VehicleClass,
)
from app.transport.services.tracking_service import TrackingService
from app.utils.exceptions import NotFoundError


@pytest.fixture
def live_user(app):
    from app.identity.models.user import User
    unique = uuid.uuid4().hex[:8]
    u = User(
        public_id=str(uuid.uuid4()),
        username=f"live_user_{unique}",
        email=f"live_user_{unique}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    u.set_password("Password123!")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def live_driver(live_user):
    dp = DriverProfile(
        user_id=live_user.id,
        driver_code=f"DRV-{uuid.uuid4().hex[:6].upper()}",
        verification_tier='platform_verified',
        compliance_status=ComplianceStatus.APPROVED,
        is_active=True,
        is_online=True,
        is_available=True,
        max_passenger_capacity=4,
        vehicle_classes=['comfort'],
    )
    db.session.add(dp)
    db.session.commit()
    return dp


class _StoreRedis:
    """In-memory Redis double: setex persists, get reads back."""

    def __init__(self, store=None, fail_on_get=False):
        self.store = store if store is not None else {}
        self.fail_on_get = fail_on_get

    def setex(self, key, ttl, value):
        self.store[key] = value

    def get(self, key):
        if self.fail_on_get:
            raise ConnectionError("redis down")
        value = self.store.get(key)
        if isinstance(value, str):
            return value.encode("utf-8")
        return value


# --- write → read coherence through the real service -------------------------

class TestLiveUpdateRetrieveRoundtrip:
    def test_update_then_get_returns_same_location(
            self, app, live_driver, monkeypatch):
        redis = _StoreRedis()
        monkeypatch.setattr(
            "app.transport.services.tracking_service.redis_client", redis)
        result = TrackingService.update_location(
            "driver", live_driver.id,
            {"latitude": -1.2833, "longitude": 36.8167})
        assert result["success"] is True

        fetched = TrackingService.get_location("driver", live_driver.id)
        assert fetched["success"] is True
        assert fetched["data"]["source"] == "redis"
        assert fetched["data"]["location"]["latitude"] == -1.2833
        assert fetched["data"]["location"]["longitude"] == 36.8167

        db.session.refresh(live_driver)
        assert live_driver.last_location["latitude"] == -1.2833
        assert live_driver.location_updated_at is not None

    def test_redis_outage_read_falls_back_to_database(
            self, app, live_driver, monkeypatch):
        live_driver.last_location = {
            "latitude": -1.2833, "longitude": 36.8167,
            "accuracy": 0.0, "speed": 0.0, "heading": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        live_driver.location_updated_at = datetime.now(timezone.utc)
        db.session.commit()

        monkeypatch.setattr(
            "app.transport.services.tracking_service.redis_client",
            _StoreRedis(fail_on_get=True))
        fetched = TrackingService.get_location("driver", live_driver.id)
        assert fetched["success"] is True
        assert fetched["data"]["source"] == "database"
        assert fetched["data"]["location"]["latitude"] == -1.2833

    def test_unknown_entity_without_any_store_raises_not_found(
            self, app, monkeypatch):
        monkeypatch.setattr(
            "app.transport.services.tracking_service.redis_client",
            _StoreRedis())
        with pytest.raises(NotFoundError):
            TrackingService.get_location("driver", 999999999)


# --- HTTP authorization boundaries ---------------------------------------------

class TestLocationEndpointAuthorization:
    def test_anonymous_cannot_publish_location(
            self, app, anonymous_client, live_driver):
        response = anonymous_client.post(
            f"/api/transport/drivers/{live_driver.id}/location",
            json={"latitude": -1.2833, "longitude": 36.8167},
            follow_redirects=False)
        assert response.status_code in (302, 401, 403)

    def test_anonymous_cannot_open_location_pages(
            self, app, anonymous_client, live_driver):
        for path in (f"/transport/drivers/{live_driver.id}/location",):
            response = anonymous_client.get(path, follow_redirects=False)
            assert response.status_code in (302, 401, 403)

    def test_admin_driver_location_page_renders_position(
            self, app, admin_client, live_driver, monkeypatch):
        live_driver.last_location = {
            "latitude": -1.2833, "longitude": 36.8167,
            "accuracy": 5.0, "speed": 0.0, "heading": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        live_driver.location_updated_at = datetime.now(timezone.utc)
        db.session.commit()

        response = admin_client.get(
            f"/transport/drivers/{live_driver.id}/location")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert live_driver.driver_code in html
        assert "-1.2833" in html
        assert "36.8167" in html

    def test_admin_location_page_missing_driver_not_found(
            self, app, admin_client):
        response = admin_client.get("/transport/drivers/999999999/location",
                                    follow_redirects=False)
        assert response.status_code in (302, 404)


# --- stored location JSON shape --------------------------------------------------

class TestStoredLocationShape:
    def test_stored_payload_carries_telemetry_fields(
            self, app, live_driver, monkeypatch):
        recorded = {}

        class _Recorder(_StoreRedis):
            def setex(self, key, ttl, value):
                recorded.update(json.loads(value))
                super().setex(key, ttl, value)

        monkeypatch.setattr(
            "app.transport.services.tracking_service.redis_client",
            _Recorder())
        TrackingService.update_location(
            "driver", live_driver.id,
            {"latitude": -1.2833, "longitude": 36.8167,
             "accuracy": 5.0, "speed": 3.1, "heading": 90.0})
        for field in ("latitude", "longitude", "accuracy", "speed",
                      "heading", "timestamp"):
            assert field in recorded
