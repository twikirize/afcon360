"""MATCH-01: terminal matching-failure states.

no_match + no_supply (window expired, zero offers ever) and no_match +
all_rejected (pool exhausted), the rider-visible negative guarantee
(no "reject"/"decline"/"refuse" substring anywhere rider-visible), the
persistence invariant (reason never null when no_match), idempotency of the
terminal close, and preservation of cancel-from-CONFIRMED.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from tests.test_transport_concurrent_claim import _FakeRedis
from tests.transport.test_match01_silent_rejection import (
    _patch_redis,
    _seed_confirmed_booking,
    _seed_rider,
)

pytestmark = pytest.mark.usefixtures("db_session")


def _backdate_window(app, booking_id, minutes=5):
    from app.transport.models import Booking

    with app.app_context():
        stored = db.session.get(Booking, booking_id)
        past = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        stored.confirmed_at = past
        meta = dict(stored.booking_metadata or {})
        meta["matching_started_at"] = past.isoformat()
        stored.booking_metadata = meta
        db.session.commit()


def _html(resp):
    return resp.data.decode("utf-8")


def _assert_no_forbidden_words(blob: str):
    lowered = blob.lower()
    assert "reject" not in lowered
    assert "declin" not in lowered
    assert "refus" not in lowered


class TestNoSupplyTerminal:
    def test_window_expires_with_zero_offers(self, app, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from app.transport.services.matching_service import MatchingService

        rider_id = _seed_rider(app)
        booking_id, _ = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        _backdate_window(app, booking_id, minutes=5)
        with app.app_context():
            outcome = MatchingService.check_matching_outcome(booking_id)
            assert outcome["terminal"] is True
            assert outcome["reason"] == "no_supply"
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.NO_MATCH
            assert stored.no_match_reason == "no_supply"

    def test_fresh_window_does_not_close(self, app, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from app.transport.services.matching_service import MatchingService

        rider_id = _seed_rider(app)
        booking_id, _ = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context():
            outcome = MatchingService.check_matching_outcome(booking_id)
            assert outcome["terminal"] is False
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.CONFIRMED


class TestAllRejectedTerminal:
    def test_pool_exhausted_closes_immediately(self, app, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from app.transport.services.matching_service import MatchingService
        from app.transport.services.offer_service import OfferService

        rider_id = _seed_rider(app)
        booking_id, _ = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        pool = MatchingService._matching_pool_size()
        assert pool == 5
        with app.app_context():
            stored = db.session.get(Booking, booking_id)
            ref = stored.booking_reference
            for driver_id in range(101, 101 + pool):
                OfferService.create_offer(ref, driver_id, 500 + driver_id)
                assert OfferService.decline_offer(ref, driver_id) is True
            db.session.expire_all()
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.NO_MATCH, stored.status
            assert stored.no_match_reason == "all_rejected"

    def test_partial_declines_do_not_close_early(self, app, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from app.transport.services.offer_service import OfferService

        rider_id = _seed_rider(app)
        booking_id, _ = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context():
            stored = db.session.get(Booking, booking_id)
            ref = stored.booking_reference
            OfferService.create_offer(ref, 101, 501)
            assert OfferService.decline_offer(ref, 101) is True
            db.session.expire_all()
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.CONFIRMED
            assert stored.no_match_reason is None


class TestRiderVisibleNegative:
    def test_no_forbidden_words_during_matching(self, app, client, monkeypatch):
        from app.transport.services.offer_service import OfferService
        from tests.test_geo_rider_tracking import _rider_client

        rider_id = _seed_rider(app)
        _, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context():
            OfferService.create_offer(ref, 101, 501)
            OfferService.decline_offer(ref, 101)
        _rider_client(app, client, rider_id)
        html = _html(client.get(f"/transport/rides/{ref}"))
        _assert_no_forbidden_words(html)
        assert "Finding your driver" in html

    def test_no_forbidden_words_after_all_rejected(
            self, app, client, monkeypatch):
        from app.transport.services.matching_service import MatchingService
        from app.transport.services.offer_service import OfferService
        from tests.test_geo_rider_tracking import _rider_client

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        pool = MatchingService._matching_pool_size()
        with app.app_context():
            for driver_id in range(101, 101 + pool):
                OfferService.create_offer(ref, driver_id, 500 + driver_id)
                OfferService.decline_offer(ref, driver_id)
        _rider_client(app, client, rider_id)
        resp = client.get(f"/transport/rides/{ref}")
        assert resp.status_code == 200, resp.status_code
        html = _html(resp)
        _assert_no_forbidden_words(html)
        assert "Couldn't match this ride right now" in html
        assert "We asked the drivers near you" in html
        assert "Try again" in html
        assert "Adjust request" in html
        # Rider JSON detail for the same terminal booking.
        blob = client.get(f"/api/transport/bookings/{ref}"
                          ).get_data(as_text=True)
        _assert_no_forbidden_words(blob)

    def test_no_forbidden_words_after_no_supply(
            self, app, client, monkeypatch):
        from app.transport.services.matching_service import MatchingService
        from tests.test_geo_rider_tracking import _rider_client

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        _backdate_window(app, booking_id, minutes=5)
        with app.app_context():
            outcome = MatchingService.check_matching_outcome(booking_id)
            assert outcome["reason"] == "no_supply"
        _rider_client(app, client, rider_id)
        html = _html(client.get(f"/transport/rides/{ref}"))
        _assert_no_forbidden_words(html)
        assert "No cars available right now" in html
        assert "Try again in a few minutes" in html
        assert "Try again" in html
        assert "Adjust request" not in html


class TestPersistenceAndIdempotency:
    def test_reason_never_null_when_no_match(self, app, monkeypatch):
        from app.transport.models import Booking
        from app.transport.services.booking_service import BookingService

        rider_id = _seed_rider(app)
        booking_id, _ = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        _backdate_window(app, booking_id, minutes=5)
        with app.app_context():
            from app.transport.services.matching_service import MatchingService

            MatchingService.check_matching_outcome(booking_id)
            stored = db.session.get(Booking, booking_id)
            assert stored.status == "no_match"
            assert stored.no_match_reason is not None

    def test_mark_no_match_rejects_bad_reason(self, app, monkeypatch):
        from app.transport.services.booking_service import BookingService
        from app.utils.exceptions import ValidationError

        rider_id = _seed_rider(app)
        booking_id, _ = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context(), pytest.raises(ValidationError):
            BookingService.mark_no_match(booking_id, "bogus_reason")

    def test_mark_no_match_idempotent(self, app, monkeypatch):
        from app.transport.models import Booking
        from app.transport.services.booking_service import BookingService
        from app.transport.services.matching_service import MatchingService

        rider_id = _seed_rider(app)
        booking_id, _ = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        _backdate_window(app, booking_id, minutes=5)
        with app.app_context():
            first = MatchingService.check_matching_outcome(booking_id)
            assert first["terminal"] is True
            second = BookingService.mark_no_match(booking_id, "no_supply")
            assert second["replayed"] is True
            stored = db.session.get(Booking, booking_id)
            assert stored.no_match_reason == "no_supply"

    def test_check_constraint_rejects_bare_no_match(self, app):
        from app.transport.models import (
            Booking, ProviderType, ServiceType,
        )

        rider_id = _seed_rider(app)
        with app.app_context():
            bad = Booking(
                booking_reference=f"BAD-{uuid.uuid4().hex[:8].upper()}",
                user_id=rider_id,
                provider_type=ProviderType.INDIVIDUAL_DRIVER,
                service_type=ServiceType.ON_DEMAND,
                pickup_location={"latitude": 0.1, "longitude": 32.5},
                dropoff_location={"latitude": 0.2, "longitude": 32.6},
                pickup_time=datetime.now(timezone.utc) + timedelta(hours=1),
                passenger_count=1, base_price=Decimal("10.00"),
                subtotal=Decimal("10.00"), total_amount=Decimal("10.00"),
                final_price=Decimal("10.00"),
                status="no_match",
                no_match_reason=None,
            )
            db.session.add(bad)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


class TestCancelPreserved:
    def test_rider_cancel_from_confirmed_still_works(
            self, app, client, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from tests.test_geo_rider_tracking import _rider_client

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        _rider_client(app, client, rider_id)
        resp = client.post(f"/transport/rides/{ref}/cancel", json={})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        with app.app_context():
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.CANCELLED

    def test_admin_transition_to_cancelled_still_works(self, app, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from app.transport.services.booking_service import BookingService

        rider_id = _seed_rider(app)
        booking_id, _ = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context():
            out = BookingService.transition_status(
                booking_id, BookingStatus.CANCELLED,
                reason="admin_test", initiated_by="admin")
            assert out["booking"].status == BookingStatus.CANCELLED
