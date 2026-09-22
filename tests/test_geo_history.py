"""AFCON360 roadmap GEO-15 location observation history - contract tests.

Proves the durable GEO-owned history boundary: the real Transport
producer persists immutable observations, retrieval is chronological,
timestamps/coordinates survive exactly, current state stays distinct
from history, and retrieval is admin-gated with public references only.

Coordinate order is latitude-first everywhere; the suite pins
asymmetric points so a lat/lng swap fails loudly. No production
movement is faked: observations come from TrackingService with real
server-receive timestamps.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.geo.history import get_observations
from app.geo.models import LocationObservation

LAT_A, LNG_A = 0.3476, 32.5825  # asymmetric Kampala point (swap-detecting)
LAT_B, LNG_B = 0.3136, 32.5811  # second asymmetric point


def _seed_driver_with_user(app):
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import (ComplianceStatus, DriverProfile,
                                      VerificationTier)
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"hist_{uid}",
                    email=f"hist_{uid}@test.example.com", is_active=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        profile = DriverProfile(
            user_id=user.id, driver_code=f"HIST-{uid[:6].upper()}",
            verification_tier=VerificationTier.PENDING,
            compliance_status=ComplianceStatus.PENDING_REVIEW,
            is_active=True, is_online=True, is_available=True,
            max_passenger_capacity=4, vehicle_classes=["comfort"])
        db.session.add(profile)
        db.session.commit()
        return profile.id, profile.driver_code


def _history_url(entity_type, public_ref):
    return f"/geo/history/location/{entity_type}/{public_ref}"


# --- writer ------------------------------------------------------------------

def test_update_location_persists_observation(app):
    from app.transport.services.tracking_service import TrackingService

    driver_id, driver_code = _seed_driver_with_user(app)
    with app.app_context():
        result = TrackingService.update_location("driver", driver_id, {
            "latitude": LAT_A, "longitude": LNG_A, "accuracy": 4.0})
    assert result["success"] is True
    rows = get_observations("driver", driver_code)
    assert len(rows) == 1
    row = rows[0]
    assert row["entity_type"] == "driver"
    assert row["public_ref"] == driver_code
    assert (row["latitude"], row["longitude"]) == (LAT_A, LNG_A)
    assert row["accuracy"] == pytest.approx(4.0)
    assert row["source"] == "transport-tracking"
    assert row["observed_at"]  # real server-receive timestamp
    assert row["recorded_at"]
    assert row["public_id"]


def test_key_proof_current_is_b_history_is_a_then_b(app):
    """Observation A @ T1, B @ T2 -> current = B, history = [A, B]."""
    from app.extensions import db
    from app.transport.models import DriverProfile
    from app.transport.services.tracking_service import TrackingService

    driver_id, driver_code = _seed_driver_with_user(app)
    with app.app_context():
        TrackingService.update_location("driver", driver_id, {
            "latitude": LAT_A, "longitude": LNG_A})
        TrackingService.update_location("driver", driver_id, {
            "latitude": LAT_B, "longitude": LNG_B})
        current = db.session.get(DriverProfile, driver_id).last_location
    assert (current["latitude"], current["longitude"]) == (LAT_B, LNG_B)
    rows = get_observations("driver", driver_code)
    assert len(rows) == 2
    assert (rows[0]["latitude"], rows[0]["longitude"]) == (LAT_A, LNG_A)
    assert (rows[1]["latitude"], rows[1]["longitude"]) == (LAT_B, LNG_B)
    t1 = datetime.fromisoformat(rows[0]["observed_at"])
    t2 = datetime.fromisoformat(rows[1]["observed_at"])
    assert t1 < t2  # chronological, source timestamps preserved


def test_reads_never_refresh_history(app):
    from app.transport.services.tracking_service import TrackingService

    driver_id, driver_code = _seed_driver_with_user(app)
    with app.app_context():
        TrackingService.update_location("driver", driver_id, {
            "latitude": LAT_A, "longitude": LNG_A})
        before = get_observations("driver", driver_code)[0]
        TrackingService.get_location("driver", driver_id)
        after = get_observations("driver", driver_code)[0]
    assert before["observed_at"] == after["observed_at"]
    assert before["recorded_at"] == after["recorded_at"]


def test_stale_observation_stays_truthful(app):
    from app.extensions import db
    from app.transport.services.tracking_service import TrackingService

    driver_id, driver_code = _seed_driver_with_user(app)
    old = datetime.now(timezone.utc) - timedelta(seconds=900)
    with app.app_context():
        TrackingService.update_location("driver", driver_id, {
            "latitude": LAT_A, "longitude": LNG_A})
        # Age one observation in place (simulates elapsed history time;
        # production rows age naturally - the point is retrieval keeps
        # the original timestamp instead of refreshing it).
        row = LocationObservation.query.filter_by(public_ref=driver_code).first()
        row.observed_at = old
        db.session.commit()
    rows = get_observations("driver", driver_code)
    assert len(rows) == 1
    # Same instant, regardless of session-timezone rendering.
    assert datetime.fromisoformat(rows[0]["observed_at"]) == old
    assert rows[0]["latitude"] == pytest.approx(LAT_A)


def test_vehicle_observations_use_license_plate(app):
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import Vehicle, VehicleClass
    from app.transport.services.tracking_service import TrackingService

    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        owner = User(username=f"vh_{uid}", email=f"vh_{uid}@test.example.com",
                     is_active=True)
        owner.set_password("TestPassword123!")
        db.session.add(owner)
        db.session.flush()
        vehicle = Vehicle(
            owner_type="platform", owner_id=owner.id,
            license_plate=f"UBX-{uid[:6].upper()}", make="Toyota",
            model="Hiace", year=2022, vehicle_type="van",
            vehicle_class=VehicleClass.VAN, passenger_capacity=14)
        db.session.add(vehicle)
        db.session.commit()
        vid, plate = vehicle.id, vehicle.license_plate
        result = TrackingService.update_location("vehicle", vid, {
            "latitude": LAT_B, "longitude": LNG_B})
    assert result["success"] is True
    rows = get_observations("vehicle", plate)
    assert len(rows) == 1
    assert (rows[0]["latitude"], rows[0]["longitude"]) == (LAT_B, LNG_B)


# --- retrieval contract -------------------------------------------------------

def test_no_history_returns_empty(app):
    driver_id, driver_code = _seed_driver_with_user(app)
    assert driver_id is not None
    assert get_observations("driver", driver_code) == []


def test_since_until_window_filters(app):
    from app.transport.services.tracking_service import TrackingService

    driver_id, driver_code = _seed_driver_with_user(app)
    with app.app_context():
        TrackingService.update_location("driver", driver_id, {
            "latitude": LAT_A, "longitude": LNG_A})
        TrackingService.update_location("driver", driver_id, {
            "latitude": LAT_B, "longitude": LNG_B})
        rows = get_observations("driver", driver_code)
        t1 = rows[0]["observed_at"]
    windowed = get_observations("driver", driver_code, since=t1)
    assert len(windowed) == 2  # inclusive lower bound
    after = get_observations(
        "driver", driver_code,
        since=(datetime.fromisoformat(t1) + timedelta(seconds=1)).isoformat())
    assert after == []
    before = get_observations("driver", driver_code, until=t1)
    assert len(before) == 1
    assert before[0]["latitude"] == pytest.approx(LAT_A)


def test_invalid_scope_rejected():
    with pytest.raises(ValueError):
        get_observations("rider", "D1")
    with pytest.raises(ValueError):
        get_observations("driver", "   ")
    with pytest.raises(ValueError):
        get_observations("driver", "D1", limit="many")
    with pytest.raises(ValueError):
        get_observations("driver", "D1", since="not-a-time")


def test_no_internal_ids_exposed(app):
    from app.transport.services.tracking_service import TrackingService

    driver_id, driver_code = _seed_driver_with_user(app)
    assert driver_id is not None
    with app.app_context():
        TrackingService.update_location("driver", driver_id, {
            "latitude": LAT_A, "longitude": LNG_A})
    blob = json.dumps(get_observations("driver", driver_code))
    assert "driver_id" not in blob
    assert "user_id" not in blob
    assert '"id":' not in blob


# --- HTTP view -----------------------------------------------------------------

def test_history_redirects_anonymous_to_login(app, anonymous_client):
    driver_id, driver_code = _seed_driver_with_user(app)
    assert driver_id is not None
    resp = anonymous_client.get(_history_url("driver", driver_code),
                                follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_history_denies_non_admin(app, authenticated_client):
    resp = authenticated_client.get(_history_url("driver", "DRV-X"),
                                    follow_redirects=False)
    assert resp.status_code == 403


def test_history_404_on_unknown_scope_or_ref(app, admin_client):
    assert admin_client.get(_history_url("rider", "DRV-X")).status_code == 404
    assert admin_client.get(
        _history_url("driver", "NO-SUCH-DRIVER")).status_code == 404


def test_history_view_returns_chronology(app, admin_client):
    from app.transport.services.tracking_service import TrackingService

    driver_id, driver_code = _seed_driver_with_user(app)
    with app.app_context():
        TrackingService.update_location("driver", driver_id, {
            "latitude": LAT_A, "longitude": LNG_A})
        TrackingService.update_location("driver", driver_id, {
            "latitude": LAT_B, "longitude": LNG_B})
    resp = admin_client.get(_history_url("driver", driver_code))
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["count"] == 2
    assert (payload["data"][0]["latitude"],
            payload["data"][0]["longitude"]) == (LAT_A, LNG_A)
    assert (payload["data"][1]["latitude"],
            payload["data"][1]["longitude"]) == (LAT_B, LNG_B)
    assert payload["data"][0]["public_ref"] == driver_code
    blob = json.dumps(payload)
    assert "driver_id" not in blob
    assert '"id":' not in blob


def test_history_view_empty_is_honest(app, admin_client):
    driver_id, driver_code = _seed_driver_with_user(app)
    assert driver_id is not None
    resp = admin_client.get(_history_url("driver", driver_code))
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload == {"success": True, "data": [], "count": 0}


def test_history_view_rejects_bad_params(app, admin_client):
    driver_id, driver_code = _seed_driver_with_user(app)
    assert driver_id is not None
    assert admin_client.get(
        _history_url("driver", driver_code) + "?limit=many").status_code == 400
    assert admin_client.get(
        _history_url("driver", driver_code) + "?since=junk").status_code == 400
