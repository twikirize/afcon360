"""Node 3 (D2) — admin booking creation goes through the canonical builder.

Defect: ``POST /api/transport/bookings`` (``BookingListResource.post``)
ran the endpoints through ``_validate_booking_location_coordinates``
alone. That helper deliberately passes non-dicts through and lets
coordinate-less dicts through, so a bare string or an address-only dict
was persisted straight into the JSONB ``pickup_location`` /
``dropoff_location`` columns as if it were a resolved location — no
canonical builder, no 13-key snapshot, no source/method provenance.

Pinned here:
  * bare string and coordinate-less dict are rejected with the standard
    validation error (400) and create no row;
  * valid coordinates are canonicalized to the full 13-key snapshot with
    truthfully inferred direct-source provenance;
  * pickup and dropoff are handled symmetrically;
  * no forbidden provider-shaped keys leak into the stored snapshot.
"""

import uuid

import pytest

CANONICAL_KEYS = {
    "latitude", "longitude", "source", "resolution_method", "provenance",
    "label", "display_name", "identity_status", "area", "accuracy_m",
    "confidence", "observed_at", "resolved_at",
}
FORBIDDEN_KEYS = {
    "address", "place_ref", "synthetic", "coordinates_resolved",
    "identity_resolved",
}


def _user_id(app, test_user):
    """Read the internal id off a committed/detached fixture user.

    The test_user fixture commits and returns a detached instance, so
    plain attribute access raises DetachedInstanceError. merge() re-binds
    a copy to the current session (same pattern as the idempotency suite).
    """
    from app.extensions import db
    with app.app_context():
        merged = db.session.merge(test_user)
        uid = merged.id
        db.session.rollback()
        return uid


def _base_payload(user_id):
    return {
        "user_id": user_id,
        "service_type": "on_demand",
        "provider_type": "individual_driver",
        "pickup_location": {"latitude": 0.3136, "longitude": 32.5811},
        "dropoff_location": {"latitude": 0.3476, "longitude": 32.5825},
        "pickup_time": "2026-12-31T10:00:00",
        "passenger_count": 2,
        "base_price": 50000,
        "subtotal": 50000,
        "total_amount": 50000,
        "final_price": 50000,
    }


def _booking_count(app):
    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        count = Booking.query.filter_by(is_deleted=False).count()
        db.session.rollback()
        return count


def _post(admin_client, payload):
    return admin_client.post("/api/transport/bookings", json=payload)


def test_admin_post_rejects_bare_string_location(app, admin_client, test_user):
    before = _booking_count(app)
    payload = _base_payload(_user_id(app, test_user))
    payload["pickup_location"] = "Kampala Road, Kampala"

    resp = _post(admin_client, payload)
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert "latitude" in resp.get_json()["error"]
    assert _booking_count(app) == before


def test_admin_post_rejects_coordinate_less_location(app, admin_client,
                                                     test_user):
    before = _booking_count(app)
    payload = _base_payload(_user_id(app, test_user))
    payload["dropoff_location"] = {"address": "Kololo, Kampala"}

    resp = _post(admin_client, payload)
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert "latitude" in resp.get_json()["error"]
    assert _booking_count(app) == before


def test_admin_post_canonicalizes_valid_coordinates(app, admin_client,
                                                    test_user):
    payload = _base_payload(_user_id(app, test_user))
    resp = _post(admin_client, payload)
    assert resp.status_code == 201, resp.get_data(as_text=True)

    data = resp.get_json()["data"]
    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        booking = Booking.query.filter_by(
            booking_reference=data["booking_reference"], is_deleted=False
        ).first()
        pickup = dict(booking.pickup_location)
        dropoff = dict(booking.dropoff_location)
        db.session.rollback()

    for snapshot in (pickup, dropoff):
        assert set(snapshot) == CANONICAL_KEYS, sorted(snapshot)
        # Bare coordinates carry no evidence of their own; the builder
        # infers the truthful direct-coordinate pair.
        assert snapshot["source"] == "map"
        assert snapshot["resolution_method"] == "map_pin"
        assert isinstance(snapshot["latitude"], float)
        assert isinstance(snapshot["longitude"], float)
        assert isinstance(snapshot["label"], str) and snapshot["label"]


def test_admin_post_pickup_and_dropoff_are_symmetric(app, admin_client,
                                                     test_user):
    payload = _base_payload(_user_id(app, test_user))
    resp = _post(admin_client, payload)
    assert resp.status_code == 201, resp.get_data(as_text=True)

    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        booking = Booking.query.filter_by(
            booking_reference=resp.get_json()["data"]["booking_reference"],
            is_deleted=False,
        ).first()
        pickup = dict(booking.pickup_location)
        dropoff = dict(booking.dropoff_location)
        db.session.rollback()

    assert set(pickup) == set(dropoff), (sorted(pickup), sorted(dropoff))
    assert pickup["source"] == dropoff["source"]
    assert pickup["resolution_method"] == dropoff["resolution_method"]
    assert pickup["identity_status"] == dropoff["identity_status"]


def test_admin_post_stores_no_forbidden_provider_keys(app, admin_client,
                                                      test_user):
    payload = _base_payload(_user_id(app, test_user))
    resp = _post(admin_client, payload)
    assert resp.status_code == 201, resp.get_data(as_text=True)

    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        booking = Booking.query.filter_by(
            booking_reference=resp.get_json()["data"]["booking_reference"],
            is_deleted=False,
        ).first()
        pickup = dict(booking.pickup_location)
        dropoff = dict(booking.dropoff_location)
        db.session.rollback()

    for snapshot in (pickup, dropoff):
        leaked = FORBIDDEN_KEYS & set(snapshot)
        assert not leaked, leaked


def test_admin_post_rejects_mismatched_source_method_pair(app, admin_client,
                                                          test_user):
    before = _booking_count(app)
    payload = _base_payload(_user_id(app, test_user))
    payload["pickup_location"] = {
        "latitude": 0.3136, "longitude": 32.5811,
        "source": "gps", "resolution_method": "map_pin",
    }

    resp = _post(admin_client, payload)
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert _booking_count(app) == before


def test_admin_post_rejects_unsatisfiable_source_claim(app, admin_client,
                                                       test_user):
    """A search claim with no provider evidence must not be persisted."""
    before = _booking_count(app)
    payload = _base_payload(_user_id(app, test_user))
    payload["dropoff_location"] = {
        "latitude": 0.3476, "longitude": 32.5825,
        "source": "search", "resolution_method": "forward_geocode",
    }

    resp = _post(admin_client, payload)
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert _booking_count(app) == before


def test_admin_post_requires_admin_role(app, client, test_user):
    """@admin_required is preserved on the mutating endpoint."""
    from tests.conftest import _login_client
    _login_client(client, test_user)
    payload = _base_payload(_user_id(app, test_user))
    resp = _post(client, payload)
    assert resp.status_code in (302, 401, 403), resp.status_code
