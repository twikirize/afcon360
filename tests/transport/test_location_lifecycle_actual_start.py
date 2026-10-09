"""Item 3 — ACTUAL_START lifecycle events (behavioral proof).

Proves through the REAL driver trip endpoint
(POST /api/transport/drivers/me/trips/<id|ref>/status {"action":"start"})
on the PostgreSQL test database (never the dev database):

  * PICKUP_ARRIVED -> IN_PROGRESS records exactly one ACTUAL_START
    (endpoint pickup, snapshot None, correct booking/driver linkage);
  * a fresh driver observation is referenced by its public_id and no
    observation row is created by the capture;
  * missing/stale observations still record the event (honest metadata);
  * retry, wrong-state, wrong-driver and non-driver attempts create no
    event;
  * commit failure rolls back status and event together;
  * the admin status path can complete the same transition with NO event
    (traced bypass, pinned behaviorally).

Harness (seeding, claim, trip calls, login) mirrors
tests/test_transport_d5_execution_lifecycle.py.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.geo.models import LocationObservation
from app.transport.models import (
    Booking,
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
    _trips_ref,
)


def _drive_to_arrived(drv_client, booking_id):
    for action in ("en_route", "arrive"):
        resp = _trips(drv_client, booking_id, action)
        assert resp.status_code == 200, resp.get_json()


def _fresh_observation(app, profile_id, driver_code):
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
        public_id = obs.public_id
        db.session.rollback()
        return public_id


def _stale_observation(app, driver_code):
    with app.app_context():
        obs = LocationObservation.query.filter_by(
            entity_type="driver", public_ref=driver_code,
            is_deleted=False).order_by(
            LocationObservation.observed_at.desc()).first()
        assert obs is not None
        obs.observed_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.session.commit()
        public_id = obs.public_id
        db.session.rollback()
        return public_id


def _events(app, booking_id, event_type="ACTUAL_START"):
    with app.app_context():
        rows = LocationLifecycleEvent.query.filter_by(
            booking_id=booking_id, event_type=event_type,
            is_deleted=False).all()
        out = [{
            "endpoint": e.endpoint,
            "snapshot": e.snapshot,
            "actor_user_id": e.actor_user_id,
            "booking_id": e.booking_id,
            "transition_at": e.transition_at,
            "geo_observation_public_id": e.geo_observation_public_id,
            "event_metadata": dict(e.event_metadata or {}),
            "public_id": e.public_id,
        } for e in rows]
        db.session.rollback()
        return out


def _obs_count(app):
    with app.app_context():
        count = LocationObservation.query.filter_by(
            is_deleted=False).count()
        db.session.rollback()
        return count


def _setup_arrived(app, label="as"):
    """Rider + driver + vehicle + booking, claimed and driven to
    PICKUP_ARRIVED through the real endpoint. Returns ids + clients."""
    pax_id = _create_user(app, f"pax{label}")
    drv_user, drv = _create_driver(app, f"d{label}")
    veh = _create_vehicle(app, drv, f"v{label}")
    bk_id, bk_ref = _create_booking(app, pax_id, f"b{label}")
    _claim(app, bk_ref, drv, veh)
    drv_client = app.test_client()
    _login_client(drv_client, drv_user)
    _drive_to_arrived(drv_client, bk_id)
    assert _bk_field(app, bk_id, "status") == BookingStatus.PICKUP_ARRIVED.value
    with app.app_context():
        from app.transport.models import DriverProfile
        code = db.session.get(DriverProfile, drv).driver_code
        db.session.rollback()
    return {"pax": pax_id, "user": drv_user, "profile": drv,
            "vehicle": veh, "booking": bk_id, "ref": bk_ref,
            "client": drv_client, "code": code}


def test_start_records_single_actual_start_with_fresh_observation(
        app, client):
    s = _setup_arrived(app, "as1")
    obs_public_id = _fresh_observation(app, s["profile"], s["code"])
    obs_before = _obs_count(app)

    before = datetime.now(timezone.utc)
    resp = _trips(s["client"], s["booking"], "start")
    after = datetime.now(timezone.utc)

    assert resp.status_code == 200, resp.get_json()
    assert _bk_field(app, s["booking"], "status") == BookingStatus.IN_PROGRESS.value

    events = _events(app, s["booking"])
    assert len(events) == 1
    event = events[0]
    assert event["endpoint"] == "pickup"
    assert event["snapshot"] is None
    assert event["booking_id"] == s["booking"]
    assert event["actor_user_id"] == s["user"]
    assert before <= event["transition_at"] <= after
    assert event["geo_observation_public_id"] == obs_public_id
    assert event["event_metadata"]["freshness"] == "fresh"
    assert event["event_metadata"]["reason"] is None
    assert event["event_metadata"]["captured_by"] == "driver_trip_action_start"
    assert event["public_id"]
    # Capture references the existing observation; it creates none.
    assert _obs_count(app) == obs_before


def test_start_without_observation_still_records(app, client):
    s = _setup_arrived(app, "as2")
    resp = _trips(s["client"], s["booking"], "start")
    assert resp.status_code == 200, resp.get_json()

    events = _events(app, s["booking"])
    assert len(events) == 1
    assert events[0]["geo_observation_public_id"] is None
    assert events[0]["event_metadata"]["freshness"] == "missing"
    assert events[0]["event_metadata"]["reason"] == "no_observation"


def test_start_with_stale_observation_links_honestly(app, client):
    s = _setup_arrived(app, "as3")
    _fresh_observation(app, s["profile"], s["code"])
    stale_id = _stale_observation(app, s["code"])

    resp = _trips(s["client"], s["booking"], "start")
    assert resp.status_code == 200, resp.get_json()

    events = _events(app, s["booking"])
    assert len(events) == 1
    assert events[0]["geo_observation_public_id"] == stale_id
    assert events[0]["event_metadata"]["freshness"] == "stale"
    assert (events[0]["event_metadata"]["reason"]
            == "stale_beyond_threshold")


def test_retry_start_creates_no_duplicate(app, client):
    s = _setup_arrived(app, "as4")
    _fresh_observation(app, s["profile"], s["code"])

    first = _trips(s["client"], s["booking"], "start")
    assert first.status_code == 200
    retry = _trips(s["client"], s["booking"], "start")
    assert retry.status_code == 409
    assert _bk_field(app, s["booking"], "status") == BookingStatus.IN_PROGRESS.value
    assert len(_events(app, s["booking"])) == 1


def test_wrong_state_start_creates_no_event(app, client):
    s = _setup_arrived(app, "as5")
    with app.app_context():
        from app.transport.models import Booking as _B
        booking = db.session.get(_B, s["booking"])
        booking.status = BookingStatus.ASSIGNED
        db.session.commit()
        db.session.rollback()
    resp = _trips(s["client"], s["booking"], "start")
    assert resp.status_code == 409
    assert _events(app, s["booking"]) == []


def test_wrong_driver_start_forbidden_without_event(app, client):
    s = _setup_arrived(app, "as6")
    other_user, _ = _create_driver(app, "dAs6b")
    other_client = app.test_client()
    _login_client(other_client, other_user)

    resp = _trips(other_client, s["booking"], "start")
    assert resp.status_code == 403
    assert _bk_field(app, s["booking"], "status") == BookingStatus.PICKUP_ARRIVED.value
    assert _events(app, s["booking"]) == []


def test_non_driver_start_forbidden_without_event(app, client, test_user):
    s = _setup_arrived(app, "as7")
    user_client = app.test_client()
    _login_client(user_client, test_user)

    resp = _trips(user_client, s["booking"], "start")
    assert resp.status_code == 403
    assert _events(app, s["booking"]) == []


def test_reference_variant_records_event(app, client):
    s = _setup_arrived(app, "as8")
    _fresh_observation(app, s["profile"], s["code"])

    resp = _trips_ref(s["client"], s["ref"], "start")
    assert resp.status_code == 200, resp.get_json()
    events = _events(app, s["booking"])
    assert len(events) == 1
    assert events[0]["endpoint"] == "pickup"
    assert events[0]["snapshot"] is None
    assert events[0]["actor_user_id"] == s["user"]


def test_commit_failure_rolls_back_status_and_event(
        app, client, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    s = _setup_arrived(app, "as9")
    _fresh_observation(app, s["profile"], s["code"])

    real_commit = db.session.commit

    def _fail_once():
        db.session.commit = real_commit
        raise SQLAlchemyError("simulated commit failure")

    monkeypatch.setattr(db.session, "commit", _fail_once)
    resp = _trips(s["client"], s["booking"], "start")
    assert resp.status_code == 500
    assert _bk_field(app, s["booking"], "status") == BookingStatus.PICKUP_ARRIVED.value
    assert _events(app, s["booking"]) == []


def test_admin_transition_bypasses_actual_start(app, client, test_admin):
    """Traced bypass (Item 3 scope note): the admin status endpoint can
    complete PICKUP_ARRIVED -> IN_PROGRESS with NO lifecycle event.
    Pinned behaviorally; operator-decision pending, not silently fixed."""
    from tests.test_transport_d5_execution_lifecycle import _admin_status
    s = _setup_arrived(app, "as10")

    admin_client = app.test_client()
    _login_client(admin_client, test_admin)
    resp = _admin_status(admin_client, s["booking"],
                        BookingStatus.IN_PROGRESS.value)
    assert resp.status_code == 200, resp.get_json()
    assert _bk_field(app, s["booking"], "status") == BookingStatus.IN_PROGRESS.value
    assert _events(app, s["booking"]) == []
