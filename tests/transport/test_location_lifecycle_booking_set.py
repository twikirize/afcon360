"""Item 2 — BOOKING_LOCATION_SET lifecycle events (behavioral proof).

Proves through the REAL BookingService.create_booking path (PostgreSQL
test database; never the dev database):

  * a successful booking durably records exactly two
    BOOKING_LOCATION_SET events (pickup + dropoff) in the SAME commit
    as the booking row;
  * each event snapshot IS the canonical 13-key ResolvedLocation
    (equal to the persisted Booking snapshot, source/method/provenance
    preserved, unknown quality left unknown);
  * idempotent replay returns the existing booking without new events;
  * failed creation persists neither booking nor events (atomicity,
    including a forced commit failure).
"""

import json
import uuid
from datetime import datetime, timezone

import pytest

from app.transport.models import Booking, LocationLifecycleEvent

THIRTEEN = [
    "latitude", "longitude", "source", "resolution_method",
    "provenance", "label", "display_name", "identity_status",
    "area", "accuracy_m", "confidence", "observed_at", "resolved_at",
]

_PICKUP = (0.3136, 32.5811)
_DROPOFF = (0.3476, 32.5825)


def _user_id(app, test_user):
    from app.extensions import db
    with app.app_context():
        merged = db.session.merge(test_user)
        uid = merged.id
        db.session.rollback()
        return uid


def _payload(**over):
    data = {
        "pickup_location": "Nakawa Riders Pickup Point",
        "dropoff_location": "Entebbe Airside Gate",
        "pickup_latitude": _PICKUP[0],
        "pickup_longitude": _PICKUP[1],
        "dropoff_latitude": _DROPOFF[0],
        "dropoff_longitude": _DROPOFF[1],
        "service_type": "on_demand",
        "pickup_time": "2026-12-31T10:00:00",
        "passenger_count": 2,
        "currency": "USD",
        "vehicle_class": "comfort",
        "payment_method": "cash",
        "idempotency_key": f"lle-{uuid.uuid4().hex}",
    }
    data.update(over)
    return data


def _create(app, user_id, data):
    from app.transport.services.booking_service import BookingService
    with app.app_context():
        return BookingService().create_booking(
            user_id, data, request_id=f"test-{data['idempotency_key']}"
        )["data"]["booking_reference"]


def _booking_row(app, reference):
    from app.extensions import db
    with app.app_context():
        booking = Booking.query.filter_by(
            booking_reference=reference, is_deleted=False).first()
        assert booking is not None, f"no booking row for {reference}"
        row = (booking.id, booking.user_id, dict(booking.pickup_location),
               dict(booking.dropoff_location))
        db.session.rollback()
        return row


def _events_for(app, booking_id):
    from app.extensions import db
    with app.app_context():
        events = LocationLifecycleEvent.query.filter_by(
            booking_id=booking_id, is_deleted=False
        ).order_by(LocationLifecycleEvent.endpoint.asc()).all()
        rows = [{
            "endpoint": e.endpoint,
            "event_type": e.event_type,
            "snapshot": dict(e.snapshot) if e.snapshot else None,
            "actor_user_id": e.actor_user_id,
            "booking_id": e.booking_id,
            "transition_at": e.transition_at,
            "parent_public_id": e.parent_public_id,
            "geo_observation_public_id": e.geo_observation_public_id,
            "event_metadata": dict(e.event_metadata or {}),
            "public_id": e.public_id,
        } for e in events]
        db.session.rollback()
        return rows


def _event_count(app):
    from app.extensions import db
    with app.app_context():
        count = LocationLifecycleEvent.query.filter_by(
            is_deleted=False).count()
        db.session.rollback()
        return count


def _booking_count(app, key, user_id):
    from app.extensions import db
    with app.app_context():
        count = Booking.query.filter_by(
            idempotency_key=key, user_id=user_id,
            is_deleted=False).count()
        db.session.rollback()
        return count


def test_success_creates_exactly_two_lifecycle_events(app, test_user):
    """One booking -> exactly {pickup, dropoff} x BOOKING_LOCATION_SET,
    same commit, canonical snapshots verbatim."""
    user_id = _user_id(app, test_user)
    data = _payload(pickup_source="gps", dropoff_source="map")
    reference = _create(app, user_id, data)

    booking_id, owner_id, pickup, dropoff = _booking_row(app, reference)
    assert owner_id == user_id

    events = _events_for(app, booking_id)
    assert len(events) == 2
    assert {e["endpoint"] for e in events} == {"pickup", "dropoff"}
    assert {e["event_type"] for e in events} == {"BOOKING_LOCATION_SET"}

    by_endpoint = {e["endpoint"]: e for e in events}
    assert by_endpoint["pickup"]["snapshot"] == pickup
    assert by_endpoint["dropoff"]["snapshot"] == dropoff

    for endpoint, snap in (("pickup", pickup), ("dropoff", dropoff)):
        assert sorted(snap.keys()) == sorted(THIRTEEN)
        event = by_endpoint[endpoint]
        assert event["snapshot"] is not None
        assert event["actor_user_id"] == user_id
        assert event["booking_id"] == booking_id
        assert event["transition_at"] is not None
        assert event["transition_at"].tzinfo is not None
        assert event["parent_public_id"] is None
        assert event["geo_observation_public_id"] is None
        assert event["event_metadata"] == {"created_by": "booking_service"}
        assert event["public_id"]

    assert by_endpoint["pickup"]["snapshot"]["source"] == "gps"
    assert (by_endpoint["pickup"]["snapshot"]["resolution_method"]
            == "browser_geolocation")
    assert by_endpoint["dropoff"]["snapshot"]["source"] == "map"
    assert (by_endpoint["dropoff"]["snapshot"]["resolution_method"]
            == "map_pin")
    # Unknown quality stays unknown — never fabricated as zero.
    for snap in (pickup, dropoff):
        assert snap["provenance"] is None
        assert snap["accuracy_m"] is None
        assert snap["confidence"] is None

    assert by_endpoint["pickup"]["public_id"] != (
        by_endpoint["dropoff"]["public_id"])


def test_search_evidence_flows_into_lifecycle_snapshot(app, test_user):
    """Item-1 meaning is preserved in the event: search provenance,
    label, identity and coordinates land verbatim in the snapshot."""
    user_id = _user_id(app, test_user)
    candidate = {
        "label": "Nakawa Riders Pickup Point, Kampala, Uganda",
        "latitude": _PICKUP[0],
        "longitude": _PICKUP[1],
        "provider": "photon",
        "osm_type": "N",
        "osm_id": 12345,
    }
    data = _payload(
        pickup_location="Nakawa Riders Pickup Point, Kampala, Uganda",
        pickup_source="search",
        pickup_geocode=json.dumps(candidate),
        dropoff_source="map",
    )
    reference = _create(app, user_id, data)
    booking_id, _, pickup, _ = _booking_row(app, reference)

    events = _events_for(app, booking_id)
    assert len(events) == 2
    snap = next(
        e["snapshot"] for e in events if e["endpoint"] == "pickup")
    assert snap == pickup
    assert snap["source"] == "search"
    assert snap["resolution_method"] == "forward_geocode"
    assert snap["provenance"] == {"authority": "photon",
                                  "reference": "N/12345"}
    assert snap["label"] == "Nakawa Riders Pickup Point, Kampala, Uganda"
    assert snap["display_name"] == (
        "Nakawa Riders Pickup Point, Kampala, Uganda")
    assert snap["identity_status"] == "unverified"
    assert snap["latitude"] == _PICKUP[0]
    assert snap["longitude"] == _PICKUP[1]


def test_idempotent_replay_creates_no_new_events(app, test_user):
    """Same key + same user -> existing booking returned; the lifecycle
    pair is not duplicated."""
    user_id = _user_id(app, test_user)
    data = _payload(pickup_source="gps", dropoff_source="map")
    first = _create(app, user_id, data)

    from app.transport.services.booking_service import BookingService
    with app.app_context():
        replay = BookingService().create_booking(
            user_id, data, request_id=f"replay-{data['idempotency_key']}")
    assert replay["success"] is True
    assert replay["data"]["booking_reference"] == first

    booking_id, _, _, _ = _booking_row(app, first)
    assert len(_events_for(app, booking_id)) == 2
    assert _booking_count(app, data["idempotency_key"], user_id) == 1


def test_failed_creation_creates_no_booking_or_events(app, test_user):
    """Validation failure before any write: no booking row, no events."""
    from app.utils.exceptions import ValidationError

    from app.transport.services.booking_service import BookingService
    user_id = _user_id(app, test_user)
    before = _event_count(app)
    data = _payload(pickup_latitude=None, pickup_longitude=None)
    key = data["idempotency_key"]

    with app.app_context():
        with pytest.raises(ValidationError):
            BookingService().create_booking(
                user_id, data, request_id=f"test-{key}")

    assert _booking_count(app, key, user_id) == 0
    assert _event_count(app) == before


def test_commit_failure_rolls_back_booking_and_events(app, test_user,
                                                      monkeypatch):
    """Atomicity: if the commit fails, neither the booking nor its
    lifecycle pair survives."""
    from sqlalchemy.exc import SQLAlchemyError

    from app.extensions import db
    from app.transport.services.booking_service import BookingService
    from app.utils.exceptions import ServiceUnavailableError
    user_id = _user_id(app, test_user)
    before = _event_count(app)
    data = _payload(pickup_source="gps", dropoff_source="map")
    key = data["idempotency_key"]

    real_commit = db.session.commit

    def _fail_once():
        db.session.commit = real_commit
        raise SQLAlchemyError("simulated commit failure")

    monkeypatch.setattr(db.session, "commit", _fail_once)
    with app.app_context():
        with pytest.raises(ServiceUnavailableError):
            BookingService().create_booking(
                user_id, data, request_id=f"test-{key}")

    assert _booking_count(app, key, user_id) == 0
    assert _event_count(app) == before
