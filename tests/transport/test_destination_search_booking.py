"""Rider discovery — mixed map-pickup + search-dropoff booking seam.

The discovery journey's canonical end state: pickup resolved by map pin,
destination resolved by a selected `/geo/api/geocode` candidate echoed in
`dropoff_geocode`. The booking seam already supports both prefixes
symmetrically; this pins the mixed combination the rider UI produces:

  * pickup  -> source="map" / resolution_method="map_pin" (no evidence)
  * dropoff -> source="search" / resolution_method="forward_geocode"
    (provider evidence mandatory, H2)

and the negative: a `dropoff_source="search"` claim without
`dropoff_geocode` evidence is a field-precise client error with no row.
"""

import json
import uuid

import pytest

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
        "pickup_location": "Pinned pickup",
        "dropoff_location": "Acacia Mall, Kampala, Uganda",
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
        "idempotency_key": f"dest-{uuid.uuid4().hex}",
    }
    data.update(over)
    return data


def _create(app, user_id, data):
    from app.transport.services.booking_service import BookingService
    with app.app_context():
        return BookingService().create_booking(
            user_id, data, request_id=f"test-{data['idempotency_key']}"
        )["data"]["booking_reference"]


def _snapshots(app, reference):
    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        booking = Booking.query.filter_by(
            booking_reference=reference, is_deleted=False
        ).first()
        assert booking is not None, f"no booking row for {reference}"
        pickup = dict(booking.pickup_location)
        dropoff = dict(booking.dropoff_location)
        db.session.rollback()
        return pickup, dropoff


def _count(app, key, user_id):
    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        count = Booking.query.filter_by(
            idempotency_key=key, user_id=user_id, is_deleted=False
        ).count()
        db.session.rollback()
        return count


def test_map_pickup_plus_search_dropoff_persists(app, test_user):
    """The discovery combination: map pickup needs no evidence, the
    search destination carries the echoed candidate."""
    user_id = _user_id(app, test_user)
    candidate = {
        "label": "Acacia Mall, Kampala, Uganda",
        "latitude": _DROPOFF[0],
        "longitude": _DROPOFF[1],
        "provider": "photon",
        "osm_type": "N",
        "osm_id": 67890,
    }
    data = _payload(
        pickup_source="map",
        dropoff_source="search",
        dropoff_geocode=json.dumps(candidate),
    )
    reference = _create(app, user_id, data)

    pickup, dropoff = _snapshots(app, reference)
    assert pickup["source"] == "map"
    assert pickup["resolution_method"] == "map_pin"
    assert dropoff["source"] == "search"
    assert dropoff["resolution_method"] == "forward_geocode"
    assert dropoff["latitude"] == _DROPOFF[0]
    assert dropoff["longitude"] == _DROPOFF[1]
    assert dropoff["provenance"]["authority"] == "photon"
    assert dropoff["provenance"]["reference"] == "N/67890"


def test_search_dropoff_without_evidence_fails_and_creates_no_row(
        app, test_user):
    """H2, dropoff side: search claim without dropoff_geocode evidence
    is a field-precise client error — no row is created."""
    from app.utils.exceptions import ValidationError

    user_id = _user_id(app, test_user)
    data = _payload(pickup_source="map", dropoff_source="search")
    key = data["idempotency_key"]

    with app.app_context():
        with pytest.raises(ValidationError) as excinfo:
            from app.transport.services.booking_service import (
                BookingService)
            BookingService().create_booking(
                user_id, data, request_id=f"test-{key}")

    assert excinfo.value.field == "dropoff_source"
    assert "dropoff_geocode provider evidence" in str(excinfo.value)
    assert _count(app, key, user_id) == 0
