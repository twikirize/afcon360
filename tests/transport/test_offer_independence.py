"""OFFER-INDEPENDENCE (Phase 2: offer-collision fix).

Before the fix one shared ``transport:offer:{booking_ref}`` hash meant
driver A's accept/decline overwrote the offer being shown to driver B on
the same booking. Every write is now scoped to a per-driver hash
``transport:offer:{booking_ref}:{driver_id}``; the winning driver's offer
is consumed on a successful claim and the losing driver's offer stays
live until they decline or expire.

Pure-fake tests (no DB) prove the isolation / CAS / cleanup semantics;
DB-backed tests prove the real dispatch -> accept -> claim flow leaves the
losing driver's offer independent and live.
"""

import uuid

import pytest

from app.transport.models import (
    Booking,
    DriverProfile,
    DriverVehicleHistory,
    Vehicle,
)
from app.transport.services.assignment_service import (
    AssignmentService,
    DispatchClaimError,
)
from app.transport.services.offer_service import (
    OFFER_STATUS_ACCEPTED,
    OfferService,
)
from tests.test_transport_concurrent_claim import (
    _FakeRedis,
    _create_booking,
    _create_user,
    _delete,
    _make_matchable_driver,
)


def _patch_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(
        "app.transport.services.offer_service.redis_client", fake)
    return fake


def _ref(prefix="IND"):
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


class TestOfferIndependence:
    """Pure-fake store semantics: offers are independent per driver."""

    def test_two_drivers_hold_independent_offers(self, monkeypatch):
        fake = _patch_redis(monkeypatch)
        ref = _ref()
        OfferService.create_offer(ref, 10, 101, ttl=300)
        OfferService.create_offer(ref, 30, 301, ttl=300)

        o10 = OfferService.get_offer(ref, 10)
        o30 = OfferService.get_offer(ref, 30)
        assert o10["status"] == "offered" and o10["driver_id"] == 10
        assert o30["status"] == "offered" and o30["driver_id"] == 30

        live = OfferService.get_offer(ref)
        assert live is not None and live["driver_id"] in (10, 30)

        assert fake.scard(OfferService._index_key(ref)) == 2
        assert fake.smembers(OfferService._driver_key(10)) == {ref}
        assert fake.smembers(OfferService._driver_key(30)) == {ref}

    def test_accept_does_not_disturb_other_driver(self, monkeypatch):
        fake = _patch_redis(monkeypatch)
        ref = _ref()
        OfferService.create_offer(ref, 10, 101, ttl=300)
        OfferService.create_offer(ref, 30, 301, ttl=300)

        accepted = OfferService.accept_offer(ref, 10)
        assert accepted["accepted"] is True
        assert OfferService.get_offer(ref, 10)["status"] == OFFER_STATUS_ACCEPTED

        # Driver 30's offer is untouched and still the live booking-wide one.
        o30 = OfferService.get_offer(ref, 30)
        assert o30 is not None and o30["status"] == "offered"
        live = OfferService.get_offer(ref)
        assert live is not None and live["driver_id"] == 30
        # Winner removed from index, loser retained.
        index = fake.smembers(OfferService._index_key(ref))
        assert "30" in index and "10" not in index

    def test_two_accepts_succeed_independently(self, monkeypatch):
        _patch_redis(monkeypatch)
        ref = _ref()
        OfferService.create_offer(ref, 10, 101, ttl=300)
        OfferService.create_offer(ref, 30, 301, ttl=300)

        assert OfferService.accept_offer(ref, 10)["accepted"] is True
        assert OfferService.accept_offer(ref, 30)["accepted"] is True
        assert OfferService.get_offer(ref, 10)["status"] == OFFER_STATUS_ACCEPTED
        assert OfferService.get_offer(ref, 30)["status"] == OFFER_STATUS_ACCEPTED
        # Both consumed -> booking-wide has no live offer left.
        assert OfferService.get_offer(ref) is None

    def test_wrong_driver_conflict_keeps_other_offer(self, monkeypatch):
        fake = _patch_redis(monkeypatch)
        ref = _ref()
        OfferService.create_offer(ref, 10, 101, ttl=300)

        with pytest.raises(DispatchClaimError) as exc_info:
            OfferService.accept_offer(ref, 99)
        assert exc_info.value.kind == "offer_conflict"
        assert OfferService.get_offer(ref, 10) is not None

    def test_scoped_cleanup_removes_only_one_driver(self, monkeypatch):
        fake = _patch_redis(monkeypatch)
        ref = _ref()
        OfferService.create_offer(ref, 10, 101, ttl=300)
        OfferService.create_offer(ref, 30, 301, ttl=300)

        OfferService.cleanup_offer(ref, 10)
        assert OfferService.get_offer(ref, 10) is None
        assert fake.smembers(OfferService._driver_key(10)) == set()
        o30 = OfferService.get_offer(ref, 30)
        assert o30 is not None and o30["status"] == "offered"
        assert fake.smembers(OfferService._driver_key(30)) == {ref}
        assert OfferService.get_offer(ref) is not None

    def test_booking_wide_cleanup_removes_every_driver(self, monkeypatch):
        fake = _patch_redis(monkeypatch)
        ref = _ref()
        OfferService.create_offer(ref, 10, 101, ttl=300)
        OfferService.create_offer(ref, 30, 301, ttl=300)

        OfferService.cleanup_offer(ref)
        assert OfferService.get_offer(ref, 10) is None
        assert OfferService.get_offer(ref, 30) is None
        assert fake.smembers(OfferService._index_key(ref)) == set()
        assert fake.smembers(OfferService._driver_key(10)) == set()
        assert fake.smembers(OfferService._driver_key(30)) == set()
        assert OfferService.get_offer(ref) is None


class TestDispatchClaimIndependence:
    """Real dispatch -> accept -> claim leaves the loser's offer live."""

    def test_claim_consumes_winner_offer_keeps_loser(self, app, monkeypatch):
        fake = _patch_redis(monkeypatch)
        pax_id = _create_user(app, "paxOind")
        _, drv1, veh1, hist1 = _make_matchable_driver(app, "oi1")
        _, drv2, veh2, hist2 = _make_matchable_driver(app, "oi2")
        bk_id, bk_ref = _create_booking(app, pax_id, "oind")

        with app.app_context():
            from app.transport.services.matching_service import MatchingService

            outcome = MatchingService.discover_and_offer(bk_id, max_candidates=2)
        assert outcome["offers_created"] >= 1, outcome

        offered = {
            int(x) for x in fake.smembers(OfferService._index_key(bk_ref))
        }
        ours = [d for d in (drv1, drv2) if d in offered]
        assert ours, f"neither of our drivers was offered: {offered}"
        winner = ours[0]
        winner_veh = veh1 if winner == drv1 else veh2
        if len(ours) == 2:
            loser = ours[1]
        else:
            loser = drv1 if winner == drv2 else drv2
            loser_veh = veh1 if loser == drv1 else veh2
            OfferService.create_offer(bk_ref, loser, loser_veh, ttl=300)

        accepted = OfferService.accept_offer(bk_ref, winner)
        assert accepted["accepted"] is True
        with app.app_context():
            AssignmentService.claim(bk_ref, winner, winner_veh, actor=None)

        # Winner's per-driver offer is consumed by the claim-time cleanup...
        assert OfferService.get_offer(bk_ref, winner) is None
        assert fake.smembers(OfferService._driver_key(winner)) == set()
        # ...and the loser's offer survives independently (still live).
        o_loser = OfferService.get_offer(bk_ref, loser)
        assert o_loser is not None and o_loser["status"] == "offered"
        assert fake.smembers(OfferService._driver_key(loser)) == {bk_ref}
        assert str(loser) in fake.smembers(OfferService._index_key(bk_ref))
        assert OfferService.get_offer(bk_ref) is not None

        # Once the loser declines, the booking is fully offer-free.
        assert OfferService.decline_offer(bk_ref, loser) is True
        assert OfferService.get_offer(bk_ref) is None

        _delete(app, (DriverVehicleHistory, hist1),
                (DriverVehicleHistory, hist2), (Booking, bk_id),
                (DriverProfile, drv1), (DriverProfile, drv2),
                (Vehicle, veh1), (Vehicle, veh2))

    def test_recovery_reoffer_does_not_duplicate_notification(
            self, app, monkeypatch):
        fake = _patch_redis(monkeypatch)
        import app.transport.services.matching_service as ms

        calls = []
        monkeypatch.setattr(
            ms, "_notify_driver_new_offer",
            lambda booking, driver_id: calls.append(driver_id))

        pax_id = _create_user(app, "paxReoff")
        _, drv, veh, hist = _make_matchable_driver(app, "orr")
        bk_id, bk_ref = _create_booking(app, pax_id, "reo")

        from app.tasks.transport_recovery import dispatch_recovery

        with app.app_context():
            r1 = dispatch_recovery()
        assert r1.get("offers_created", 0) >= 1, r1
        assert calls == [drv], calls

        with app.app_context():
            r2 = dispatch_recovery()
        assert r2.get("offers_created", 0) >= 1, r2
        # Re-advertising must NOT re-notify an already-offered driver.
        assert calls == [drv], f"second beat re-notified: {calls}"

        offer = OfferService.get_offer(bk_ref)
        assert offer is not None and offer["driver_id"] == drv
        assert fake.smembers(OfferService._driver_key(drv)) == {bk_ref}

        _delete(app, (DriverVehicleHistory, hist), (Booking, bk_id),
                (DriverProfile, drv), (Vehicle, veh))