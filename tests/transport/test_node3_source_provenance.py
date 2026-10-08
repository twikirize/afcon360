"""Node 3 (D3) — rider-form source provenance reaches the canonical snapshot.

Defect: the booking form knew *how* each endpoint was chosen (GPS fix,
map pin, search selection) but the payload carried only coordinates, so
the canonical builder could only re-infer provenance after the fact.

Correction: `pickup_source` / `dropoff_source` hidden fields travel with
the request and are handed straight to the canonical builder, which
resolves the ratified method from the pairing table. A client therefore
cannot mismatch a pair, and an unknown marker is a client error rather
than a silently invented provenance.

Pinned here:
  * gps -> gps / browser_geolocation;
  * map -> map / map_pin;
  * pickup and dropoff are symmetric;
  * an unknown source marker fails safely and creates no row;
  * an absent marker keeps the historical inference path (direct
    coordinates -> map / map_pin);
  * the form itself writes and preserves those markers (GPS, drag,
    side swap).
"""

import uuid

import pytest

from app.transport.services.location_snapshot import SOURCE_METHOD_PAIRS

RATIFIED_PAIRS = {
    "gps": "browser_geolocation",
    "map": "map_pin",
    "search": "forward_geocode",
    "curated": "registry_lookup",
}

_PICKUP = (0.3136, 32.5811)
_DROPOFF = (0.3476, 32.5825)


def _user_id(app, test_user):
    from app.extensions import db
    with app.app_context():
        merged = db.session.merge(test_user)
        uid = merged.id
        db.session.rollback()
        return uid


def _payload(source=None, dropoff_source=None):
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
        "idempotency_key": f"d3-{uuid.uuid4().hex}",
    }
    if source is not None:
        data["pickup_source"] = source
    if dropoff_source is not None:
        data["dropoff_source"] = dropoff_source
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


def test_pairing_table_is_the_ratified_one():
    """The client never supplies a method; the table does."""
    assert dict(SOURCE_METHOD_PAIRS) == RATIFIED_PAIRS


def test_gps_and_map_markers_reach_the_canonical_snapshot(app, test_user):
    user_id = _user_id(app, test_user)
    data = _payload(source="gps", dropoff_source="map")
    reference = _create(app, user_id, data)

    pickup, dropoff = _snapshots(app, reference)
    assert pickup["source"] == "gps"
    assert pickup["resolution_method"] == "browser_geolocation"
    assert dropoff["source"] == "map"
    assert dropoff["resolution_method"] == "map_pin"


def test_both_endpoints_accept_the_same_marker(app, test_user):
    user_id = _user_id(app, test_user)
    data = _payload(source="map", dropoff_source="map")
    reference = _create(app, user_id, data)

    pickup, dropoff = _snapshots(app, reference)
    for snapshot in (pickup, dropoff):
        assert snapshot["source"] == "map"
        assert snapshot["resolution_method"] == "map_pin"


def test_unknown_marker_fails_safely_and_creates_no_row(app, test_user):
    user_id = _user_id(app, test_user)
    data = _payload(source="teleport")
    key = data["idempotency_key"]

    from app.utils.exceptions import ValidationError
    with pytest.raises(ValidationError):
        _create(app, user_id, data)

    assert _count(app, key, user_id) == 0


def test_absent_marker_keeps_the_inference_path(app, test_user):
    """No marker at all: direct coordinates still resolve truthfully."""
    user_id = _user_id(app, test_user)
    data = _payload()
    reference = _create(app, user_id, data)

    pickup, dropoff = _snapshots(app, reference)
    for snapshot in (pickup, dropoff):
        assert snapshot["source"] == "map"
        assert snapshot["resolution_method"] == "map_pin"


def test_snapshot_coordinates_are_the_submitted_ones(app, test_user):
    """Provenance is carried, never used to move the coordinates."""
    user_id = _user_id(app, test_user)
    reference = _create(app, user_id, _payload(source="gps"))

    pickup, dropoff = _snapshots(app, reference)
    assert pickup["latitude"] == _PICKUP[0]
    assert pickup["longitude"] == _PICKUP[1]
    assert dropoff["latitude"] == _DROPOFF[0]
    assert dropoff["longitude"] == _DROPOFF[1]


# --- the form itself ---------------------------------------------------------

_FORM = "templates/transport/new_home.html"


def _form_source():
    from pathlib import Path
    return Path(_FORM).read_text(encoding="utf-8")


def test_form_declares_both_source_markers():
    text = _form_source()
    assert 'name="pickup_source"' in text
    assert 'name="dropoff_source"' in text


def test_form_gps_handler_records_gps():
    text = _form_source()
    assert "document.getElementById('pickup_source').value    = 'gps'" in text


def test_form_dragged_marker_records_map():
    text = _form_source()
    assert "pins[kind].src = 'map';" in text


def test_form_swap_preserves_provenance():
    text = _form_source()
    assert "var pkSrc = pk ? pk.src : null, dfSrc = df ? df.src : null;" in text
    assert "dfSrc || 'map'" in text
    assert "pkSrc || 'map'" in text
