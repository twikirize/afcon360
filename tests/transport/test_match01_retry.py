"""MATCH-01: manual "Try again" retry from no_match.

Retry reopens NO_MATCH -> CONFIRMED with a FRESH matching window (review
Condition 1: no instant re-fire), restarts matching on the SAME booking,
is booker-only, and the offer ledger stays concurrency-safe under parallel
declines (review Condition 3: single-statement atomic JSONB append).
"""
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from tests.transport.test_match01_no_match_terminals import _backdate_window
from tests.transport.test_match01_silent_rejection import (
    _patch_redis,
    _seed_confirmed_booking,
    _seed_rider,
)

pytestmark = pytest.mark.usefixtures("db_session")


def _to_no_supply(app, monkeypatch, booking_id):
    from app.transport.services.matching_service import MatchingService

    _patch_redis(monkeypatch)
    _backdate_window(app, booking_id, minutes=5)
    with app.app_context():
        outcome = MatchingService.check_matching_outcome(booking_id)
        assert outcome["reason"] == "no_supply"
        return outcome


class TestRetryMatching:
    def test_retry_reopens_with_fresh_window(self, app, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from app.transport.services.booking_service import (
            BookingService, _matching_window_start,
        )
        from app.transport.services.matching_service import MatchingService

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _to_no_supply(app, monkeypatch, booking_id)
        with app.app_context():
            before = db.session.get(Booking, booking_id)
            old_confirmed = before.confirmed_at
            out = BookingService.retry_matching(booking_id, rider_id)
            assert out["booking"].status == BookingStatus.CONFIRMED
            assert out["booking"].no_match_reason is None
            assert out["booking"].booking_reference == ref  # same booking
            fresh = _matching_window_start(out["booking"])
            assert fresh is not None
            age = (datetime.now(timezone.utc) - fresh).total_seconds()
            assert age < 60  # fresh cursor, not the backdated one
            assert out["booking"].confirmed_at >= old_confirmed
            # Condition 1 regression: the second window must run its full
            # course — an immediate re-check must NOT re-fire no_match.
            again = MatchingService.check_matching_outcome(booking_id)
            assert again["terminal"] is False
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.CONFIRMED

    def test_retry_route_restarts_matching(self, app, client, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from tests.test_geo_rider_tracking import _rider_client

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _to_no_supply(app, monkeypatch, booking_id)
        _rider_client(app, client, rider_id)
        resp = client.post(f"/transport/rides/{ref}/retry",
                           follow_redirects=False)
        assert resp.status_code in (200, 302), resp.get_data(as_text=True)
        with app.app_context():
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.CONFIRMED
            assert stored.no_match_reason is None

    def test_retry_forbidden_for_foreign_user(self, app, monkeypatch):
        from app.transport.services.booking_service import BookingService
        from app.utils.exceptions import AuthorizationError

        rider_id = _seed_rider(app)
        other_id = _seed_rider(app)
        booking_id, _ = _seed_confirmed_booking(app, rider_id)
        _to_no_supply(app, monkeypatch, booking_id)
        # NOTE: the service raises app.utils.exceptions.PermissionError,
        # which is an alias of AuthorizationError (NOT the builtin).
        with app.app_context(), pytest.raises(AuthorizationError):
            BookingService.retry_matching(booking_id, other_id)

    def test_retry_rejected_unless_no_match(self, app, monkeypatch):
        from app.transport.services.booking_service import BookingService
        from app.utils.exceptions import ValidationError

        rider_id = _seed_rider(app)
        booking_id, _ = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context(), pytest.raises(ValidationError):
            BookingService.retry_matching(booking_id, rider_id)

    def test_retry_page_shows_matching_view_again(
            self, app, client, monkeypatch):
        from tests.test_geo_rider_tracking import _rider_client

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _to_no_supply(app, monkeypatch, booking_id)
        _rider_client(app, client, rider_id)
        client.post(f"/transport/rides/{ref}/retry", follow_redirects=False)
        html = client.get(f"/transport/rides/{ref}").data.decode("utf-8")
        assert "Finding your driver" in html
        lowered = html.lower()
        assert "reject" not in lowered
        assert "declin" not in lowered
        assert "refus" not in lowered


class TestLedgerConcurrency:
    def test_parallel_declines_lose_no_entry(self, app, monkeypatch):
        """Two simultaneous ledger appends on the SAME booking row must both
        land (Condition 3). A Python read-modify-write would lose one; the
        single-statement jsonb_set append serializes on the row lock."""
        from app.transport.models import Booking
        from app.transport.services.offer_service import OfferService

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        errors = []

        def _append(driver_id):
            try:
                with app.app_context():
                    ok = OfferService.record_offer_ledger(
                        ref, driver_id, "declined")
                    assert ok is True
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=_append, args=(901,)),
                   threading.Thread(target=_append, args=(902,))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert not errors, errors
        with app.app_context():
            stored = db.session.get(Booking, booking_id)
            attempts = (stored.booking_metadata or {}).get("offer_attempts", [])
            drivers = {a.get("driver_id") for a in attempts
                       if a.get("outcome") == "declined"}
            assert {901, 902} <= drivers, attempts
