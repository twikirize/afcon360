"""Node 3: rider booking-detail payload must not expose internal Booking IDs.

The generic serializer strips only the primary key `id`; the eight
internal Booking foreign keys (plus original_provider_id) passed through
to the rider boundary. The rider surface consumes status + driver_display
only — nothing reads these FKs — so the non-admin branch of
BookingDetailResource.get strips them (dual-ID law; cf. wallet F-04).
Admin payload keeps them (proven below, unchanged behavior).
"""

import pytest

from tests.test_geo_rider_tracking import _rider_client
from tests.transport.test_match01_silent_rejection import (
    _patch_redis,
    _seed_confirmed_booking,
    _seed_rider,
)

pytestmark = pytest.mark.usefixtures("db_session")

STRIPPED_KEYS = (
    "user_id",
    "assigned_driver_id",
    "assigned_vehicle_id",
    "provider_id",
    "original_provider_id",
    "assigned_route_id",
    "event_id",
    "event_participation_id",
    "group_leader_id",
)


def _rider_payload(app, ref, rider_id):
    rider_client = app.test_client()
    _rider_client(app, rider_client, rider_id)
    resp = rider_client.get(f"/api/transport/bookings/{ref}")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["data"]["booking"]


class TestNode3RiderIdStripping:
    def test_rider_payload_omits_internal_booking_ids(
            self, app, monkeypatch):
        from app.transport.models import BookingStatus

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)

        payload = _rider_payload(app, ref, rider_id)
        for key in STRIPPED_KEYS:
            assert key not in payload, f"internal {key} leaked to rider"
        assert "id" not in payload
        # Public contract preserved: reference, status, locations.
        assert payload["booking_reference"] == ref
        assert payload["status"] == BookingStatus.CONFIRMED.value
        # Locations round-trip untouched by the stripping (the fixture
        # seeds legacy 2-key dicts; canonical 13-key shape is proven by
        # the booking-seam suites, not re-asserted here).
        from app.extensions import db
        from app.transport.models import Booking
        with app.app_context():
            stored = db.session.get(Booking, booking_id)
            assert payload["pickup_location"] == stored.pickup_location
            assert payload["dropoff_location"] == stored.dropoff_location
            db.session.rollback()

    def test_admin_payload_keeps_internal_booking_ids(
            self, app, admin_client, monkeypatch):
        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)

        with admin_client.session_transaction() as sess:
            sess["active_global_role"] = "owner"
        resp = admin_client.get(f"/api/transport/bookings/{ref}")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        payload = resp.get_json()["data"]["booking"]
        # Admin behavior unchanged: all internal identifiers remain
        # available; only the synthetic primary key stays stripped.
        assert payload["user_id"] == rider_id
        assert "assigned_driver_id" in payload
        assert "assigned_vehicle_id" in payload
        assert "provider_id" in payload
        assert "original_provider_id" in payload
        assert "assigned_route_id" in payload
        assert "event_id" in payload
        assert "event_participation_id" in payload
        assert "group_leader_id" in payload
        assert "id" not in payload
        assert payload["booking_reference"] == ref
