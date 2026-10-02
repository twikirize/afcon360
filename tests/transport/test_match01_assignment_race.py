"""MATCH-01: assignment-vs-NO_MATCH race (control-authorized gap test).

Both orderings run through the REAL transactional guards
(AssignmentService.claim r1 + BookingService.mark_no_match guarded UPDATE),
not mocks:

* claim wins  -> booking is ASSIGNED and never becomes NO_MATCH;
* NO_MATCH wins -> a later claim is rejected and no stale assignment remains.
"""
import pytest

from app.extensions import db
from tests.test_transport_concurrent_claim import (
    _create_driver,
    _create_vehicle,
)
from tests.transport.test_match01_no_match_terminals import _backdate_window
from tests.transport.test_match01_silent_rejection import (
    _patch_redis,
    _seed_confirmed_booking,
    _seed_rider,
)

pytestmark = pytest.mark.usefixtures("db_session")


class TestAssignmentVsNoMatchRace:
    def test_claim_wins_race_never_becomes_no_match(
            self, app, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from app.transport.services.assignment_service import (
            AssignmentService,
            DispatchClaimError,
        )
        from app.transport.services.booking_service import BookingService
        from app.transport.services.matching_service import MatchingService
        from app.utils.exceptions import ValidationError

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _, driver_id = _create_driver(app, "race1")
        vehicle_id = _create_vehicle(app, driver_id, "race1")
        _patch_redis(monkeypatch)
        with app.app_context():
            AssignmentService.claim(ref, driver_id, vehicle_id, actor=None)
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.ASSIGNED
            # The matching close path must not touch an assigned booking.
            outcome = MatchingService.check_matching_outcome(booking_id)
            assert outcome["terminal"] is False
            assert outcome["reason"] == "not_awaiting_matching"
            with pytest.raises(ValidationError):
                BookingService.mark_no_match(booking_id, "no_supply")
            db.session.expire_all()
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.ASSIGNED
            assert stored.no_match_reason is None

    def test_no_match_wins_race_claim_rejected_no_stale_assignment(
            self, app, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from app.transport.services.assignment_service import (
            AssignmentService,
            DispatchClaimError,
        )
        from app.transport.services.matching_service import MatchingService

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _, driver_id = _create_driver(app, "race2")
        vehicle_id = _create_vehicle(app, driver_id, "race2")
        _patch_redis(monkeypatch)
        _backdate_window(app, booking_id, minutes=5)
        with app.app_context():
            outcome = MatchingService.check_matching_outcome(booking_id)
            assert outcome["terminal"] is True
            assert outcome["reason"] == "no_supply"
            with pytest.raises(DispatchClaimError) as exc:
                AssignmentService.claim(ref, driver_id, vehicle_id,
                                        actor=None)
            assert exc.value.kind == "booking_unavailable"
            db.session.expire_all()
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.NO_MATCH
            assert stored.no_match_reason == "no_supply"
            assert stored.assigned_driver_id is None
            assert stored.assigned_vehicle_id is None
