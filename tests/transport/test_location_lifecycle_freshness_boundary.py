"""Item 5 — freshness boundary (fresh / stale / missing are metadata-only).

Pins the documented 120s freshness threshold used by the ACTUAL_START
(driver_routes._capture_actual_start) and ACTUAL_END
(assignment_service._capture_actual_end) captures:

  * an observation ~115s old is "fresh";
  * an observation ~125s old is "stale" with reason
    "stale_beyond_threshold", still linked by public_id;
  * age_at_transition is recorded in event_metadata;
  * stale freshness NEVER blocks the status transition
    (IN_PROGRESS / COMPLETED are still reached).

Fresh-vs-missing-vs-2h-stale behavior is already proven in
test_location_lifecycle_actual_start.py and
test_location_lifecycle_actual_end.py; this file pins the threshold
boundary only. See DFD-04 (120s hardcoded, metadata-only).

Threshold precision note: observations are aged ~115 s and ~125 s with
a ±10 s age assertion window. This proves the two sides of the 120 s
implementation threshold, not the exact 120 s boundary, and it is not
approval of the threshold value (see DFD-04).
"""

from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.geo.models import LocationObservation
from app.transport.models import (
    BookingStatus,
    LocationLifecycleEvent,
)
from tests.test_transport_d5_execution_lifecycle import (
    _bk_field,
    _claim,
    _create_booking,
    _create_driver,
    _create_user,
    _create_vehicle,
    _login_client,
    _trips,
)

FRESH_AGE_SECONDS = 115
STALE_AGE_SECONDS = 125


def _aged_observation(app, profile_id, driver_code, age_seconds):
    """Create a real driver observation, then backdate it by age_seconds."""
    from app.transport.services.tracking_service import TrackingService
    with app.app_context():
        TrackingService.update_location(
            "driver", profile_id,
            {"latitude": 0.3476, "longitude": 32.5825, "accuracy": 5.0})
    with app.app_context():
        obs = LocationObservation.query.filter_by(
            entity_type="driver", public_ref=driver_code,
            is_deleted=False).order_by(
            LocationObservation.observed_at.desc()).first()
        assert obs is not None
        obs.observed_at = (datetime.now(timezone.utc)
                           - timedelta(seconds=age_seconds))
        db.session.commit()
        public_id = obs.public_id
        db.session.rollback()
        return public_id


def _events(app, booking_id, event_type):
    with app.app_context():
        rows = LocationLifecycleEvent.query.filter_by(
            booking_id=booking_id, event_type=event_type,
            is_deleted=False).all()
        out = [{
            "geo_observation_public_id": e.geo_observation_public_id,
            "event_metadata": dict(e.event_metadata or {}),
        } for e in rows]
        db.session.rollback()
        return out


def _setup_arrived(app, label):
    pax_id = _create_user(app, f"pax{label}")
    drv_user, drv = _create_driver(app, f"d{label}")
    veh = _create_vehicle(app, drv, f"v{label}")
    bk_id, bk_ref = _create_booking(app, pax_id, f"b{label}")
    _claim(app, bk_ref, drv, veh)
    drv_client = app.test_client()
    _login_client(drv_client, drv_user)
    for action in ("en_route", "arrive"):
        resp = _trips(drv_client, bk_id, action)
        assert resp.status_code == 200, resp.get_json()
    assert _bk_field(app, bk_id, "status") == BookingStatus.PICKUP_ARRIVED.value
    with app.app_context():
        from app.transport.models import DriverProfile
        code = db.session.get(DriverProfile, drv).driver_code
        db.session.rollback()
    return {"user": drv_user, "profile": drv, "booking": bk_id,
            "client": drv_client, "code": code}


def _setup_progress(app, label):
    s = _setup_arrived(app, label)
    resp = _trips(s["client"], s["booking"], "start")
    assert resp.status_code == 200, resp.get_json()
    assert _bk_field(app, s["booking"], "status") == BookingStatus.IN_PROGRESS.value
    return s


def test_start_115s_observation_is_fresh(app):
    s = _setup_arrived(app, "fb1")
    obs_id = _aged_observation(app, s["profile"], s["code"],
                               FRESH_AGE_SECONDS)
    resp = _trips(s["client"], s["booking"], "start")
    assert resp.status_code == 200, resp.get_json()
    assert _bk_field(app, s["booking"], "status") == BookingStatus.IN_PROGRESS.value
    events = _events(app, s["booking"], "ACTUAL_START")
    assert len(events) == 1
    assert events[0]["geo_observation_public_id"] == obs_id
    meta = events[0]["event_metadata"]
    assert meta["freshness"] == "fresh"
    assert meta["reason"] is None
    assert FRESH_AGE_SECONDS - 10 <= meta["age_at_transition"] <= FRESH_AGE_SECONDS + 10


def test_start_125s_observation_is_stale_but_unblocked(app):
    s = _setup_arrived(app, "fb2")
    obs_id = _aged_observation(app, s["profile"], s["code"],
                               STALE_AGE_SECONDS)
    resp = _trips(s["client"], s["booking"], "start")
    assert resp.status_code == 200, resp.get_json()
    # Stale GPS must not block the driver's Start trip action.
    assert _bk_field(app, s["booking"], "status") == BookingStatus.IN_PROGRESS.value
    events = _events(app, s["booking"], "ACTUAL_START")
    assert len(events) == 1
    assert events[0]["geo_observation_public_id"] == obs_id
    meta = events[0]["event_metadata"]
    assert meta["freshness"] == "stale"
    assert meta["reason"] == "stale_beyond_threshold"
    assert STALE_AGE_SECONDS - 10 <= meta["age_at_transition"] <= STALE_AGE_SECONDS + 10


def test_end_115s_observation_is_fresh(app):
    s = _setup_progress(app, "fb3")
    obs_id = _aged_observation(app, s["profile"], s["code"],
                               FRESH_AGE_SECONDS)
    resp = _trips(s["client"], s["booking"], "complete")
    assert resp.status_code == 200, resp.get_json()
    assert _bk_field(app, s["booking"], "status") == BookingStatus.COMPLETED.value
    events = _events(app, s["booking"], "ACTUAL_END")
    assert len(events) == 1
    assert events[0]["geo_observation_public_id"] == obs_id
    meta = events[0]["event_metadata"]
    assert meta["freshness"] == "fresh"
    assert FRESH_AGE_SECONDS - 10 <= meta["age_at_transition"] <= FRESH_AGE_SECONDS + 10


def test_end_125s_observation_is_stale_but_unblocked(app):
    s = _setup_progress(app, "fb4")
    obs_id = _aged_observation(app, s["profile"], s["code"],
                               STALE_AGE_SECONDS)
    resp = _trips(s["client"], s["booking"], "complete")
    assert resp.status_code == 200, resp.get_json()
    # Stale GPS must not block the driver's Complete trip action.
    assert _bk_field(app, s["booking"], "status") == BookingStatus.COMPLETED.value
    events = _events(app, s["booking"], "ACTUAL_END")
    assert len(events) == 1
    assert events[0]["geo_observation_public_id"] == obs_id
    meta = events[0]["event_metadata"]
    assert meta["freshness"] == "stale"
    assert meta["reason"] == "stale_beyond_threshold"
    assert STALE_AGE_SECONDS - 10 <= meta["age_at_transition"] <= STALE_AGE_SECONDS + 10
