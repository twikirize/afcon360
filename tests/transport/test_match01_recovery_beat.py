"""MATCH-01: recovery-beat close path (control-authorized gap test).

Proves ``transport.dispatch_recovery`` closes an expired CONFIRMED
matching window as NO_MATCH/no_supply (check-then-rediscover) without
creating a second booking and without bypassing assignment guards.
The recovery implementation is unchanged.
"""
import pytest

from app.extensions import db
from tests.transport.test_match01_no_match_terminals import _backdate_window
from tests.transport.test_match01_silent_rejection import (
    _patch_redis,
    _seed_confirmed_booking,
    _seed_rider,
)

pytestmark = pytest.mark.usefixtures("db_session")


class TestRecoveryBeatClosePath:
    def test_beat_closes_expired_window_as_no_supply(
            self, app, monkeypatch):
        from app.tasks.transport_recovery import dispatch_recovery
        from app.transport.models import Booking, BookingStatus

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        _backdate_window(app, booking_id, minutes=5)
        with app.app_context():
            before = db.session.query(Booking).count()
            result = dispatch_recovery()
            closed = result.get("no_match_closed") or []
            assert any(c.get("reason") == "no_supply"
                       for c in closed), result
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.NO_MATCH
            assert stored.no_match_reason == "no_supply"
            assert stored.assigned_driver_id is None
            assert stored.assigned_vehicle_id is None
            assert db.session.query(Booking).count() == before, \
                "beat must not create a second booking"

    def test_beat_leaves_fresh_matching_window_open(
            self, app, monkeypatch):
        from app.tasks.transport_recovery import dispatch_recovery
        from app.transport.models import Booking, BookingStatus

        rider_id = _seed_rider(app)
        booking_id, _ = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context():
            dispatch_recovery()
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.CONFIRMED
            assert stored.no_match_reason is None
