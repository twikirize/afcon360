"""AFCON360 roadmap GEO-17 Demand / Activity Layers - contract tests.

Proves the domain-neutral aggregation boundary: grid-cell binning math,
deterministic concentration ordering, activity derived from GEO-15
observations, demand derived from Transport booking requests (Transport
decides which bookings count), required explicit windows, admin-gated
cells views, and no leakage of raw movements or internal IDs.

SUPPLY vs ACTIVITY vs DEMAND stay separate: an online driver with no
observations contributes to neither activity nor demand (Transport owns
availability meaning). No demand is fabricated: empty windows yield
empty cells.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest

from app.geo.activity import (
    aggregate_cells,
    cell_center,
    cell_key_for,
    get_activity,
)
from app.utils.exceptions import ValidationError

LAT, LNG = 0.3136, 32.5811  # asymmetric Kampala point (swap-detecting)


def _window(minutes=3):
    """Tight window: isolates this run's rows from other tests' seeds."""
    now = datetime.now(timezone.utc)
    return (now - timedelta(minutes=minutes)).isoformat(), now.isoformat()


def _q(value):
    return quote(value, safe="")


def _seed_driver(app, code_prefix="ACT"):
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import (ComplianceStatus, DriverProfile,
                                      VerificationTier)
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"{code_prefix.lower()}_{uid}",
                    email=f"{code_prefix.lower()}_{uid}@test.example.com",
                    is_active=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        profile = DriverProfile(
            user_id=user.id, driver_code=f"{code_prefix}-{uid[:6].upper()}",
            verification_tier=VerificationTier.PENDING,
            compliance_status=ComplianceStatus.PENDING_REVIEW,
            is_active=True, is_online=True, is_available=True,
            max_passenger_capacity=4, vehicle_classes=["comfort"])
        db.session.add(profile)
        db.session.commit()
        return profile.id, profile.driver_code


def _seed_booking(app, user_id, ref, lat, lng, status, created_at,
                  pickup=None):
    from decimal import Decimal
    from app.extensions import db
    from app.transport.models import Booking, ProviderType, ServiceType
    with app.app_context():
        booking = Booking(
            booking_reference=ref, user_id=user_id,
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            pickup_location=(pickup if pickup is not None
                             else {"latitude": lat, "longitude": lng}),
            dropoff_location={"latitude": lat + 0.01,
                              "longitude": lng + 0.01},
            pickup_time=datetime.now(timezone.utc) + timedelta(hours=1),
            passenger_count=1, service_type=ServiceType.ON_DEMAND,
            base_price=Decimal("10.00"), subtotal=Decimal("10.00"),
            total_amount=Decimal("10.00"), final_price=Decimal("10.00"),
            status=status, created_at=created_at)
        db.session.add(booking)
        db.session.commit()
        return booking.id


# --- cell math -----------------------------------------------------------------

def test_cell_key_format_and_center_roundtrip():
    key = cell_key_for(LAT, LNG)
    assert key == "0.31,32.58"
    center = cell_center(key)
    assert center == {"latitude": 0.31, "longitude": 32.58}


def test_cell_key_negative_zero_normalized():
    assert cell_key_for(-0.001, -0.001) == "0.00,0.00"
    assert cell_key_for(-0.001, -0.001) == cell_key_for(0.001, 0.001)


def test_cell_key_rejects_invalid():
    with pytest.raises(ValidationError):
        cell_key_for(91.0, 0.0)
    with pytest.raises(ValidationError):
        cell_key_for("north", LNG)
    with pytest.raises(ValidationError):
        cell_center("not-a-cell")


def test_aggregate_counts_distinct_orders_deterministically():
    agg = aggregate_cells([
        (LAT, LNG, "drv-a"), (LAT, LNG, "drv-a"), (LAT, LNG, "drv-b"),
        (1.0, 33.0, "drv-c"),
    ])
    assert agg["skipped_invalid"] == 0
    assert agg["truncated"] is False
    assert len(agg["cells"]) == 2
    top, second = agg["cells"]
    assert top["count"] == 3 and top["distinct"] == 2  # count desc
    assert second["count"] == 1
    assert top["center"]["latitude"] == pytest.approx(0.31)


def test_aggregate_tiebreak_is_cell_key_order():
    agg = aggregate_cells([(0.10, 30.0, "x"), (0.50, 30.0, "y")])
    assert [c["cell_key"] for c in agg["cells"]] == ["0.10,30.00",
                                                    "0.50,30.00"]


def test_aggregate_skips_invalid_and_reports():
    agg = aggregate_cells([
        (LAT, LNG, "ok"), (999.0, 0.0, "bad"), ("x", LNG, "bad"),
        (None, None, "bad"),
    ])
    assert agg["skipped_invalid"] == 3
    assert len(agg["cells"]) == 1
    assert agg["cells"][0]["count"] == 1


def test_aggregate_empty_is_truthful():
    assert aggregate_cells([]) == {"cells": [], "skipped_invalid": 0,
                                   "truncated": False}


def test_aggregate_truncation_capped_and_flagged():
    points = [(float(i % 89), float(i % 179), f"e{i}") for i in range(250)]
    agg = aggregate_cells(points)
    assert agg["truncated"] is True
    assert len(agg["cells"]) == 200


# --- activity service ------------------------------------------------------------

def test_activity_counts_observations_and_entities(app):
    from app.transport.services.tracking_service import TrackingService

    # Unique cell per test: the shared test DB accumulates seeds.
    lat, lng = 7.00, 42.00
    driver_a, _ = _seed_driver(app, "ACTA")
    driver_b, _ = _seed_driver(app, "ACTB")
    with app.app_context():
        TrackingService.update_location("driver", driver_a, {
            "latitude": lat, "longitude": lng})
        TrackingService.update_location("driver", driver_a, {
            "latitude": lat, "longitude": lng})
        TrackingService.update_location("driver", driver_b, {
            "latitude": lat, "longitude": lng})
    since, until = _window()
    payload = get_activity("driver", since=since, until=until)
    cell = next(c for c in payload["cells"]
                if c["cell_key"] == "7.00,42.00")
    assert cell["observation_count"] == 3
    assert cell["entity_count"] == 2  # observed entities, not availability
    assert payload["window"] == {"since": since, "until": until}
    assert payload["computed_at"]
    assert payload["truncated"] is False


def test_activity_window_excludes_outside_observations(app):
    from app.extensions import db
    from app.geo.models import LocationObservation
    from app.transport.services.tracking_service import TrackingService

    driver_id, driver_code = _seed_driver(app, "ACTW")
    lat, lng = 6.00, 41.00
    with app.app_context():
        TrackingService.update_location("driver", driver_id, {
            "latitude": lat, "longitude": lng})
        old = LocationObservation(
            entity_type="driver", public_ref=driver_code,
            latitude=lat, longitude=lng, accuracy=5.0,
            observed_at=datetime.now(timezone.utc) - timedelta(hours=5),
            source="transport-tracking")
        db.session.add(old)
        db.session.commit()
    since, until = _window(minutes=30)
    payload = get_activity("driver", since=since, until=until)
    cell = next(c for c in payload["cells"]
                if c["cell_key"] == "6.00,41.00")
    assert cell["observation_count"] == 1  # old row excluded


def test_activity_requires_explicit_window():
    with pytest.raises(ValueError):
        get_activity("driver", since=None, until=None)
    with pytest.raises(ValueError):
        get_activity("driver", since="junk",
                     until=datetime.now(timezone.utc).isoformat())
    with pytest.raises(ValueError):
        get_activity("rider", since="2026-01-01T00:00:00+00:00",
                     until="2026-01-02T00:00:00+00:00")


def test_activity_bbox_filters(app):
    from app.transport.services.tracking_service import TrackingService

    driver_id, _ = _seed_driver(app, "ACTC")
    lat, lng = 8.00, 43.00
    with app.app_context():
        TrackingService.update_location("driver", driver_id, {
            "latitude": lat, "longitude": lng})
    since, until = _window()
    everywhere = get_activity("driver", since=since, until=until)
    assert any(c["cell_key"] == "8.00,43.00"
               for c in everywhere["cells"])
    elsewhere = get_activity("driver", since=since, until=until, bbox={
        "min_latitude": 10.0, "max_latitude": 11.0,
        "min_longitude": 10.0, "max_longitude": 11.0})
    assert elsewhere["cells"] == []
    with pytest.raises(ValueError):
        get_activity("driver", since=since, until=until,
                     bbox={"min_latitude": 5.0, "max_latitude": 4.0,
                           "min_longitude": 0.0, "max_longitude": 1.0})


def test_online_driver_without_observations_contributes_nothing(app):
    """SUPPLY vs ACTIVITY vs DEMAND: presence (online) is Transport
    meaning; GEO activity/demand derive only from recorded signals."""
    driver_id, _ = _seed_driver(app, "ACTD")
    assert driver_id is not None
    since, until = _window()
    payload = get_activity("driver", since=since, until=until, bbox={
        "min_latitude": 60.0, "max_latitude": 61.0,
        "min_longitude": 60.0, "max_longitude": 61.0})
    assert payload["cells"] == []


# --- demand provider + view --------------------------------------------------------

def test_booking_provider_counts_and_excludes(app):
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import BookingStatus
    from app.transport.services.booking_service import booking_request_points

    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"dem_{uid}", email=f"dem_{uid}@test.example.com",
                    is_active=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    now = datetime.now(timezone.utc)
    lat, lng = 9.10, 44.10
    _seed_booking(app, user_id, f"DEM-{uid[:4]}-C", lat, lng,
                  BookingStatus.CONFIRMED, now - timedelta(minutes=1))
    _seed_booking(app, user_id, f"DEM-{uid[:4]}-D", lat, lng,
                  BookingStatus.DRAFT, now - timedelta(minutes=1))
    _seed_booking(app, user_id, f"DEM-{uid[:4]}-X", lat, lng,
                  BookingStatus.CANCELLED, now - timedelta(minutes=1))
    _seed_booking(app, user_id, f"DEM-{uid[:4]}-B", lat, lng,
                  BookingStatus.CONFIRMED, now - timedelta(minutes=1),
                  pickup={"address": "no coords"})
    since, until = _window()
    with app.app_context():
        points, skipped = booking_request_points(since, until)
    ours = [p for p in points
            if abs(p[0] - lat) < 1e-9 and abs(p[1] - lng) < 1e-9]
    assert len(ours) == 1  # only the confirmed, canonical request
    assert skipped >= 1  # address-only pickup skipped truthfully


def _demand_url(since, until):
    return f"/geo/demand/cells?since={_q(since)}&until={_q(until)}"


def _activity_url(since, until):
    return f"/geo/activity/cells?since={_q(since)}&until={_q(until)}"


def test_cells_views_redirect_anonymous(app, anonymous_client):
    # NOTE: never combine anonymous + authenticated clients in one test:
    # fixtures share the function-scoped `client`, so "anonymous" would
    # inherit a login session (same gotcha as GEO-14 SSE tests).
    since, until = _window()
    assert anonymous_client.get(
        _activity_url(since, until),
        follow_redirects=False).status_code in (302, 401)
    assert anonymous_client.get(
        _demand_url(since, until),
        follow_redirects=False).status_code in (302, 401)


def test_cells_views_deny_non_admin(app, authenticated_client):
    since, until = _window()
    assert authenticated_client.get(
        _activity_url(since, until),
        follow_redirects=False).status_code == 403
    assert authenticated_client.get(
        _demand_url(since, until),
        follow_redirects=False).status_code == 403


def test_cells_views_reject_missing_window(app, admin_client):
    since, until = _window()
    assert admin_client.get(
        "/geo/activity/cells").status_code == 400  # window required
    assert admin_client.get(
        _demand_url("junk", until)).status_code == 400


def test_demand_view_counts_requests(app, admin_client):
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import BookingStatus

    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"demv_{uid}",
                    email=f"demv_{uid}@test.example.com", is_active=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    now = datetime.now(timezone.utc)
    lat, lng = 9.20, 44.20
    _seed_booking(app, user_id, f"DMV-{uid[:4]}-1", lat, lng,
                  BookingStatus.CONFIRMED, now - timedelta(minutes=1))
    _seed_booking(app, user_id, f"DMV-{uid[:4]}-2", lat + 0.001, lng,
                  BookingStatus.ASSIGNED, now - timedelta(minutes=1))
    since, until = _window()
    resp = admin_client.get(_demand_url(since, until))
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    cell = next(c for c in payload["cells"]
                if c["cell_key"] == "9.20,44.20")
    assert cell == {
        "cell_key": "9.20,44.20",
        "center": {"latitude": 9.2, "longitude": 44.2},
        "request_count": 2,
    }
    assert payload["window"] == {"since": since, "until": until}
    blob = json.dumps(payload)
    assert "driver_id" not in blob and '"id":' not in blob


def test_activity_view_empty_is_honest(app, admin_client):
    since, until = _window()
    resp = admin_client.get(
        _activity_url(since, until)
        + "&min_latitude=50&max_latitude=51"
          "&min_longitude=50&max_longitude=51")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["cells"] == []
    assert payload["success"] is True
