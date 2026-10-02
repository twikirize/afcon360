"""MATCH-01 / Phase 1: API serialization regression.

After the BookingStatus ENUM→String conversion, the booking status in the
ACTUAL JSON/HTTP rider response must remain the lowercase string value
(e.g. "confirmed", "no_match") — byte-identical to the pre-conversion
contract. Tests the real endpoint, not just to_dict().
"""
import pytest

from app.extensions import db
from tests.transport.test_match01_silent_rejection import (
    _patch_redis,
    _seed_confirmed_booking,
    _seed_rider,
)

pytestmark = pytest.mark.usefixtures("db_session")


class TestStatusJsonContract:
    def test_rider_json_status_is_lowercase_string(self, app, client):
        from app.transport.models import Booking
        from tests.test_geo_rider_tracking import _rider_client

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _rider_client(app, client, rider_id)
        resp = client.get(f"/api/transport/bookings/{ref}")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        payload = resp.get_json()["data"]["booking"]
        assert payload["status"] == "confirmed"
        assert isinstance(payload["status"], str)
        with app.app_context():
            stored = db.session.get(Booking, booking_id)
            # Storage proof: plain str, not an enum member.
            assert type(stored.status) is str
            assert stored.status == "confirmed"

    def test_rider_json_no_match_is_lowercase_string(
            self, app, client, monkeypatch):
        from app.transport.models import Booking
        from app.transport.services.matching_service import MatchingService
        from tests.test_geo_rider_tracking import _rider_client
        from tests.transport.test_match01_no_match_terminals import (
            _backdate_window,
        )

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        _backdate_window(app, booking_id, minutes=5)
        with app.app_context():
            outcome = MatchingService.check_matching_outcome(booking_id)
            assert outcome["reason"] == "no_supply"
        _rider_client(app, client, rider_id)
        resp = client.get(f"/api/transport/bookings/{ref}")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        payload = resp.get_json()["data"]["booking"]
        assert payload["status"] == "no_match"
        assert isinstance(payload["status"], str)
