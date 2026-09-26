"""
tests/test_transport_concurrent_claim.py
TH-3-D2: Canonical atomic claim/release concurrency tests.

Proves the five D2 concurrency contracts:

  T1  Two drivers race for one CONFIRMED booking  -> exactly one wins
  T2  One driver races for two CONFIRMED bookings  -> exactly one wins
  T3  One vehicle races for two CONFIRMED bookings -> exactly one wins
  T4  Cancel-vs-claim races (both orderings)       -> cancel always wins
  T5  Late release never frees another booking's driver/vehicle

Plus negatives: double release, repeated claim, force-by-non-admin,
soft-delete rejection, offer CAS, stall recovery.

These tests are marked ``@pytest.mark.threaded`` so conftest
``_isolate_db`` skips them; each test self-cleans inserted rows
in a finally block.
"""
import uuid
from datetime import datetime, timedelta, timezone
from threading import Barrier, Thread

import pytest

from app.extensions import db
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
    ServiceType,
    Vehicle,
    VehicleClass,
)
from app.transport.services.assignment_service import (
    AssignmentService,
    DispatchClaimError,
)
from app.transport.services.offer_service import OfferService


# =====================================================================
# Minimal FakeRedis (offer service needs eval for Lua accept/decline)
# =====================================================================

class _FakeRedis:
    """In-memory Redis stand-in for offer_service tests."""

    def __init__(self):
        self._hash = {}   # {key: {field: value}}
        self._set = {}    # {key: set(str)}

    def setex(self, key, ttl, value):
        pass

    def get(self, key):
        return None

    def hset(self, key, mapping=None, **kwargs):
        m = mapping or kwargs
        d = self._hash.setdefault(key, {})
        for f, v in m.items():
            d[f] = str(v)

    def hgetall(self, key):
        return dict(self._hash.get(key, {}))

    def hget(self, key, field):
        return self._hash.get(key, {}).get(field)

    def sadd(self, key, *values):
        s = self._set.setdefault(key, set())
        before = len(s)
        for v in values:
            s.add(str(v))
        return len(s) - before

    def srem(self, key, *values):
        s = self._set.get(key, set())
        before = len(s)
        for v in values:
            s.discard(str(v))
        return 1 if len(s) < before else 0

    def smembers(self, key):
        return set(self._set.get(key, set()))

    def scard(self, key):
        return len(self._set.get(key, set()))

    def delete(self, *keys):
        for k in keys:
            self._hash.pop(k, None)
            self._set.pop(k, None)
        return 0

    def keys(self, pattern="*"):
        import fnmatch
        all_keys = set(self._hash) | set(self._set)
        if pattern == "*":
            return list(all_keys)
        return sorted(k for k in all_keys if fnmatch.fnmatch(k, pattern))

    def expire(self, key, ttl):
        pass

    def ping(self):
        return True

    def eval(self, script, numkeys, *args):
        # args = (KEYS[1..N], ARGV[1..M]) — skip numkeys key args
        script_args = args[numkeys:]
        keys_args = args[:numkeys]
        if "state ~= ARGV" in script and "owner ~= ARGV" in script:
            return self._eval_accept(script_args, keys_args)
        if "owner ~= ARGV" in script and "DEL" in script:
            return self._eval_decline(script_args, keys_args)
        raise RuntimeError("unsupported Lua script in FakeRedis")

    def _eval_accept(self, script_args, keys_args):
        driver_id_str, expected, target, booking_ref = script_args
        offer_key, driver_key, index_key = keys_args
        state = self.hget(offer_key, "status")
        if state != expected:
            return 0
        owner = self.hget(offer_key, "driver_id")
        if owner != driver_id_str:
            return 0
        self.hset(offer_key, mapping={"status": target})
        self.srem(driver_key, booking_ref)
        self.srem(index_key, driver_id_str)
        return 1

    def _eval_decline(self, script_args, keys_args):
        driver_id_str, booking_ref = script_args
        offer_key, driver_key, index_key = keys_args
        owner = self.hget(offer_key, "driver_id")
        if owner != driver_id_str:
            return 0
        self.srem(driver_key, booking_ref)
        self.srem(index_key, driver_id_str)
        self.delete(offer_key)
        return 1


# =====================================================================
# Helpers — all return integer IDs, not ORM objects
# =====================================================================

def _create_user(app, label="user"):
    with app.app_context():
        from app.identity.models.user import User
        uid = uuid.uuid4().hex[:8]
        u = User(
            username=f"{label}_{uid}",
            email=f"{label}_{uid}@test.example.com",
            is_verified=True, is_active=True,
        )
        u.set_password("TestPass123!")
        db.session.add(u)
        db.session.commit()
        return u.id


def _create_driver(app, label="drv"):
    """Create a unique user + DriverProfile. Returns (user_id, driver_id)."""
    user_id = _create_user(app, f"drv_{label}")
    with app.app_context():
        dp = DriverProfile(
            user_id=user_id,
            driver_code=f"DRV-{label}-{uuid.uuid4().hex[:6].upper()}",
            verification_tier="platform_verified",
            compliance_status=ComplianceStatus.APPROVED,
            is_active=True, is_online=True, is_available=True,
            max_passenger_capacity=4, vehicle_classes=["comfort"],
        )
        db.session.add(dp)
        db.session.commit()
        return user_id, dp.id


def _create_vehicle(app, driver_id, label="v"):
    with app.app_context():
        v = Vehicle(
            owner_type="driver", owner_id=driver_id,
            license_plate=f"UG-{label}-{uuid.uuid4().hex[:4].upper()}",
            make="Toyota", model="Corolla", year=2022,
            vehicle_type="sedan", vehicle_class=VehicleClass.COMFORT,
            passenger_capacity=4, status="active", is_available=True,
        )
        db.session.add(v)
        db.session.commit()
        return v.id


def _create_booking(app, user_id, label="bk", status=BookingStatus.CONFIRMED):
    now = datetime.now(timezone.utc)
    ref = f"REF-{label}-{uuid.uuid4().hex[:8].upper()}"
    with app.app_context():
        bk = Booking(
            booking_reference=ref, user_id=user_id,
            provider_type="individual_driver", service_type=ServiceType.ON_DEMAND,
            pickup_location={"latitude": 0.3476, "longitude": 32.5825},
            dropoff_location={"latitude": 0.3130, "longitude": 32.5812},
            pickup_time=now + timedelta(hours=2),
            base_price=100.00, subtotal=100.00,
            total_amount=100.00, final_price=100.00,
            passenger_count=1, status=status,
        )
        db.session.add(bk)
        db.session.commit()
        return bk.id, ref


def _bk_field(app, booking_id, field):
    with app.app_context():
        return getattr(db.session.get(Booking, booking_id), field)


def _drv_field(app, driver_id, field):
    with app.app_context():
        return getattr(db.session.get(DriverProfile, driver_id), field)


def _veh_field(app, vehicle_id, field):
    with app.app_context():
        return getattr(db.session.get(Vehicle, vehicle_id), field)


def _delete(app, *ids_and_types):
    """Delete rows by (model_class, id) pairs.

    Threaded tests skip _isolate_db, so they must clean up EVERY row they
    created -- including the passenger/driver User rows -- or later tests'
    teardown triggers FK violations (notifications_user_id_fkey).
    """
    with app.app_context():
        for model, oid in ids_and_types:
            obj = db.session.get(model, oid)
            if obj:
                db.session.delete(obj)
        db.session.commit()


# =====================================================================
# T1: Two drivers race for one CONFIRMED booking
# =====================================================================

@pytest.mark.threaded
class TestConcurrentDriverClaim:
    def test_two_drivers_one_booking(self, app):
        pax_id = _create_user(app, "pax")
        drv1_user, drv1 = _create_driver(app, "d1")
        drv2_user, drv2 = _create_driver(app, "d2")
        veh1 = _create_vehicle(app, drv1, "v1")
        veh2 = _create_vehicle(app, drv2, "v2")
        bk_id, bk_ref = _create_booking(app, pax_id, "t1")

        barrier = Barrier(2)
        results = [None, None]
        errors  = [None, None]

        def claim(idx, driver_id, vehicle_id):
            with app.app_context():
                barrier.wait(timeout=5)
                try:
                    results[idx] = AssignmentService.claim(
                        bk_ref, driver_id, vehicle_id, actor=None
                    )
                except DispatchClaimError as e:
                    errors[idx] = e

        t0 = Thread(target=claim, args=(0, drv1, veh1))
        t1 = Thread(target=claim, args=(1, drv2, veh2))
        t0.start(); t1.start()
        t0.join(timeout=10); t1.join(timeout=10)

        wins = sum(1 for r in results if r is not None)
        losses = sum(1 for e in errors if e is not None)
        assert wins == 1, f"Expected exactly 1 win, got {wins}"
        assert losses == 1, f"Expected exactly 1 loss, got {losses}"
        loser = errors[0] or errors[1]
        assert loser.kind == "booking_unavailable"

        _delete(app, (Booking, bk_id), (DriverProfile, drv1), (DriverProfile, drv2),
                (Vehicle, veh1), (Vehicle, veh2))


# =====================================================================
# T2: One driver races for two bookings
# =====================================================================

@pytest.mark.threaded
class TestConcurrentBookingPerDriver:
    def test_one_driver_two_bookings(self, app):
        pax_id = _create_user(app, "pax2")
        drv_user, drv = _create_driver(app, "dSolo")
        veh = _create_vehicle(app, drv, "vSolo")
        bk1_id, bk1_ref = _create_booking(app, pax_id, "t2a")
        bk2_id, bk2_ref = _create_booking(app, pax_id, "t2b")

        barrier = Barrier(2)
        results = [None, None]
        errors  = [None, None]

        def claim(idx, booking_ref):
            with app.app_context():
                barrier.wait(timeout=5)
                try:
                    results[idx] = AssignmentService.claim(
                        booking_ref, drv, veh, actor=None
                    )
                except DispatchClaimError as e:
                    errors[idx] = e

        t0 = Thread(target=claim, args=(0, bk1_ref))
        t1 = Thread(target=claim, args=(1, bk2_ref))
        t0.start(); t1.start()
        t0.join(timeout=10); t1.join(timeout=10)

        wins = sum(1 for r in results if r is not None)
        losses = sum(1 for e in errors if e is not None)
        assert wins == 1, f"Expected exactly 1 win, got {wins}"
        assert losses == 1, f"Expected exactly 1 loss, got {losses}"
        assert (errors[0] or errors[1]).kind == "driver_unavailable"

        _delete(app, (Booking, bk1_id), (Booking, bk2_id),
                (DriverProfile, drv), (Vehicle, veh))


# =====================================================================
# T3: One vehicle races for two bookings
# =====================================================================

@pytest.mark.threaded
class TestConcurrentVehicleClaim:
    def test_one_vehicle_two_bookings(self, app):
        pax_id = _create_user(app, "pax3")
        drv1_user, drv1 = _create_driver(app, "d3a")
        drv2_user, drv2 = _create_driver(app, "d3b")
        veh = _create_vehicle(app, drv1, "vShared")
        bk1_id, bk1_ref = _create_booking(app, pax_id, "t3a")
        bk2_id, bk2_ref = _create_booking(app, pax_id, "t3b")

        barrier = Barrier(2)
        results = [None, None]
        errors  = [None, None]

        def claim(idx, driver_id, booking_ref):
            with app.app_context():
                barrier.wait(timeout=5)
                try:
                    results[idx] = AssignmentService.claim(
                        booking_ref, driver_id, veh, actor=None
                    )
                except DispatchClaimError as e:
                    errors[idx] = e

        t0 = Thread(target=claim, args=(0, drv1, bk1_ref))
        t1 = Thread(target=claim, args=(1, drv2, bk2_ref))
        t0.start(); t1.start()
        t0.join(timeout=10); t1.join(timeout=10)

        wins = sum(1 for r in results if r is not None)
        losses = sum(1 for e in errors if e is not None)
        assert wins == 1, f"Expected exactly 1 win, got {wins}"
        assert losses == 1, f"Expected exactly 1 loss, got {losses}"
        assert (errors[0] or errors[1]).kind == "vehicle_unavailable"

        _delete(app, (Booking, bk1_id), (Booking, bk2_id),
                (DriverProfile, drv1), (DriverProfile, drv2), (Vehicle, veh))


# =====================================================================
# T4: Cancel vs Claim races (both orderings)
# =====================================================================

@pytest.mark.threaded
class TestConcurrentCancelVsClaim:
    def test_cancel_before_claim_wins(self, app):
        pax_id = _create_user(app, "pax4")
        drv_user, drv = _create_driver(app, "d4")
        veh = _create_vehicle(app, drv, "v4")
        bk_id, bk_ref = _create_booking(app, pax_id, "t4a")

        with app.app_context():
            bk_obj = db.session.get(Booking, bk_id)
            bk_obj.status = BookingStatus.CANCELLED.value
            db.session.commit()

        with pytest.raises(DispatchClaimError) as exc:
            with app.app_context():
                AssignmentService.claim(bk_ref, drv, veh, actor=None)
        assert exc.value.kind == "booking_unavailable"

        _delete(app, (Booking, bk_id), (DriverProfile, drv), (Vehicle, veh))

    def test_claim_before_cancel_r1_prevents_double_assign(self, app):
        pax_id = _create_user(app, "pax4b")
        drv_user, drv = _create_driver(app, "d4b")
        veh = _create_vehicle(app, drv, "v4b")
        bk_id, bk_ref = _create_booking(app, pax_id, "t4b")

        # Sequential, deterministic: claim() commits first, so the booking
        # is ASSIGNED and a later cancel cannot orphan the assignment.
        with app.app_context():
            result = AssignmentService.claim(bk_ref, drv, veh, actor=None)
        assert result["status"] == BookingStatus.ASSIGNED.value
        assert _bk_field(app, bk_id, "assigned_driver_id") == drv

        from app.transport.services.booking_service import ValidationError
        from app.transport.services.booking_service import BookingService
        with app.app_context():
            try:
                BookingService().cancel_booking(
                    booking_id=bk_id, user_id=pax_id,
                    reason="passenger change of mind",
                )
                cancelled = True
            except ValidationError:
                cancelled = False
        assert cancelled is False, (
            "Booking was claimed first, so cancel after claim must not "
            "succeed (it would orphantically release the assignment)."
        )

        # Cancel never mutated the assignment; release cleanly instead.
        with app.app_context():
            AssignmentService.release(bk_id, BookingStatus.COMPLETED, actor=None, reason="test")
        _delete(app, (Booking, bk_id), (DriverProfile, drv), (Vehicle, veh))


# =====================================================================
# T5: Late release never frees another booking's resource
# =====================================================================

@pytest.mark.threaded
class TestLateReleaseProtection:
    def test_late_release_does_not_free_reclaimed_resources(self, app):
        pax_id = _create_user(app, "pax5")
        drv_user, drv = _create_driver(app, "d5")
        veh = _create_vehicle(app, drv, "v5")
        bkA_id, bkA_ref = _create_booking(app, pax_id, "t5a")
        bkB_id, bkB_ref = _create_booking(app, pax_id, "t5b")

        # Step 1: claim booking A
        with app.app_context():
            AssignmentService.claim(bkA_ref, drv, veh, actor=None)

        # Step 2: release booking A
        with app.app_context():
            AssignmentService.release(bkA_id, BookingStatus.CANCELLED, actor=None, reason="stale")

        # Step 3: driver and vehicle should be available
        assert _drv_field(app, drv, "is_available") is True
        assert _veh_field(app, veh, "is_available") is True

        # Step 4: claim booking B
        with app.app_context():
            result_b = AssignmentService.claim(bkB_ref, drv, veh, actor=None)
        assert result_b["status"] == BookingStatus.ASSIGNED.value
        assert result_b["booking_id"] == bkB_id

        # Step 5: late release booking A — must not free B's resources
        with app.app_context():
            AssignmentService.release(bkA_id, BookingStatus.CANCELLED, actor=None, reason="late")

        # Step 6: booking B still has the driver and vehicle
        assert _bk_field(app, bkB_id, "assigned_driver_id") == drv
        assert _bk_field(app, bkB_id, "assigned_vehicle_id") == veh
        assert _bk_field(app, bkB_id, "status") == BookingStatus.ASSIGNED.value

        # Step 7: driver/vehicle still unavailable (held by B)
        assert _drv_field(app, drv, "is_available") is False
        assert _veh_field(app, veh, "is_available") is False

        # Cleanup: release B first (has FKs), then delete
        with app.app_context():
            AssignmentService.release(bkB_id, BookingStatus.COMPLETED, actor=None, reason="test")
        _delete(app, (Booking, bkA_id), (Booking, bkB_id),
                (DriverProfile, drv), (Vehicle, veh))


# =====================================================================
# Negatives (non-threaded)
# =====================================================================

class TestClaimNegatives:
    def test_double_release_is_idempotent(self, app):
        pax_id = _create_user(app, "paxDbl")
        _, drv = _create_driver(app, "dDbl")
        veh = _create_vehicle(app, drv, "vDbl")
        bk_id, bk_ref = _create_booking(app, pax_id, "tDbl")

        with app.app_context():
            AssignmentService.claim(bk_ref, drv, veh, actor=None)
            AssignmentService.release(bk_id, BookingStatus.CANCELLED, actor=None, reason="first")
            result = AssignmentService.release(bk_id, BookingStatus.CANCELLED, actor=None, reason="second")
        assert result["released"] is False

        _delete(app, (Booking, bk_id), (DriverProfile, drv), (Vehicle, veh))

    def test_claim_already_assigned_booking_rejected(self, app):
        pax_id = _create_user(app, "paxAss")
        _, drv1 = _create_driver(app, "dA1")
        _, drv2 = _create_driver(app, "dA2")
        veh1 = _create_vehicle(app, drv1, "vA1")
        veh2 = _create_vehicle(app, drv2, "vA2")
        bk_id, bk_ref = _create_booking(app, pax_id, "tAss")

        with app.app_context():
            AssignmentService.claim(bk_ref, drv1, veh1, actor=None)
        with pytest.raises(DispatchClaimError) as exc_info:
            with app.app_context():
                AssignmentService.claim(bk_ref, drv2, veh2, actor=None)
        assert exc_info.value.kind == "booking_unavailable"

        with app.app_context():
            AssignmentService.release(bk_id, BookingStatus.COMPLETED, actor=None, reason="test")
        _delete(app, (Booking, bk_id), (DriverProfile, drv1), (DriverProfile, drv2),
                (Vehicle, veh1), (Vehicle, veh2))

    def test_claim_with_force_by_non_admin_rejected(self, app):
        pax_id = _create_user(app, "paxFrc")
        user_obj_id = _create_user(app, "normal_user")
        _, drv = _create_driver(app, "dFrc")
        veh = _create_vehicle(app, drv, "vFrc")
        bk_id, bk_ref = _create_booking(app, pax_id, "tFrc")

        with app.app_context():
            from app.identity.models.user import User
            user_obj = db.session.get(User, user_obj_id)
        with pytest.raises(DispatchClaimError) as exc_info:
            with app.app_context():
                AssignmentService.claim(bk_ref, drv, veh, actor=user_obj, force=True)
        assert exc_info.value.kind == "unauthorized"

        _delete(app, (Booking, bk_id), (DriverProfile, drv), (Vehicle, veh))

    def test_soft_deleted_booking_rejected(self, app):
        pax_id = _create_user(app, "paxDel")
        _, drv = _create_driver(app, "dDel")
        veh = _create_vehicle(app, drv, "vDel")
        bk_id, bk_ref = _create_booking(app, pax_id, "tDel")

        with app.app_context():
            bk_obj = db.session.get(Booking, bk_id)
            bk_obj.is_deleted = True
            db.session.commit()

        with pytest.raises(DispatchClaimError) as exc_info:
            with app.app_context():
                AssignmentService.claim(bk_ref, drv, veh, actor=None)
        assert exc_info.value.kind == "booking_unavailable"

        _delete(app, (Booking, bk_id), (DriverProfile, drv), (Vehicle, veh))


# =====================================================================
# Offer service tests (FakeRedis)
# =====================================================================

class TestOfferService:
    def test_create_and_get_offer(self, app, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)
        ref = f"REF-OFR-{uuid.uuid4().hex[:8]}"
        offer = OfferService.create_offer(ref, driver_id=42, vehicle_id=99, ttl=300)
        assert offer["status"] == "offered"
        assert offer["driver_id"] == 42
        got = OfferService.get_offer(ref, driver_id=42)
        assert got is not None
        assert got["driver_id"] == 42

    def test_accept_offer_cas(self, app, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)
        ref = f"REF-CAS-{uuid.uuid4().hex[:8]}"
        OfferService.create_offer(ref, driver_id=10, vehicle_id=20, ttl=300)
        result = OfferService.accept_offer(ref, driver_id=10)
        assert result["accepted"] is True

        with pytest.raises(DispatchClaimError) as exc_info:
            OfferService.accept_offer(ref, driver_id=10)
        assert exc_info.value.kind == "offer_conflict"

    def test_accept_offer_expired(self, app, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)
        ref = f"REF-EXP-{uuid.uuid4().hex[:8]}"
        with pytest.raises(DispatchClaimError) as exc_info:
            OfferService.accept_offer(ref, driver_id=5)
        assert exc_info.value.kind == "offer_expired"

    def test_decline_offer(self, app, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)
        ref = f"REF-DEC-{uuid.uuid4().hex[:8]}"
        OfferService.create_offer(ref, driver_id=7, vehicle_id=8, ttl=300)
        assert OfferService.decline_offer(ref, driver_id=7) is True
        assert OfferService.get_offer(ref) is None

    def test_redis_unavailable_raises_offer_unavailable(self, app, monkeypatch):
        class DeadRedis(_FakeRedis):
            def hset(self, *a, **kw):
                raise ConnectionError("no redis")
        monkeypatch.setattr("app.transport.services.offer_service.redis_client", DeadRedis())
        with pytest.raises(Exception):
            OfferService.create_offer("REF-DEAD", driver_id=1, vehicle_id=2, ttl=60)

    def test_sweep_expired_cleans_index(self, app, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)
        ref = f"REF-SWP-{uuid.uuid4().hex[:8]}"
        OfferService.create_offer(ref, driver_id=50, vehicle_id=60, ttl=300)
        fake.delete(OfferService._offer_key(ref))
        cleared = OfferService.sweep_expired()
        assert cleared >= 1


# =====================================================================
# Stall recovery task test
# =====================================================================

class TestStallRecovery:
    def test_stall_booking_cancelled(self, app):
        pax_id = _create_user(app, "paxStall")
        _, drv = _create_driver(app, "dStall")
        veh = _create_vehicle(app, drv, "vStall")
        bk_id, bk_ref = _create_booking(app, pax_id, "tStall")

        with app.app_context():
            AssignmentService.claim(bk_ref, drv, veh, actor=None)
            bk_obj = db.session.get(Booking, bk_id)
            bk_obj.driver_assigned_at = datetime.now(timezone.utc) - timedelta(seconds=900)
            bk_obj.driver_en_route_at = None
            db.session.commit()

        from app.tasks.transport_recovery import stall_recovery
        result = stall_recovery(stall_seconds=600, dry_run=False)
        assert bk_id in result["recovered"]

        assert _bk_field(app, bk_id, "status") == BookingStatus.CANCELLED.value
        assert _bk_field(app, bk_id, "assigned_driver_id") is None
        assert _bk_field(app, bk_id, "assigned_vehicle_id") is None

        _delete(app, (Booking, bk_id), (DriverProfile, drv), (Vehicle, veh))

    def test_stall_recovery_dry_run_no_mutation(self, app):
        pax_id = _create_user(app, "paxDry")
        _, drv = _create_driver(app, "dDry")
        veh = _create_vehicle(app, drv, "vDry")
        bk_id, bk_ref = _create_booking(app, pax_id, "tDry")

        with app.app_context():
            AssignmentService.claim(bk_ref, drv, veh, actor=None)
            bk_obj = db.session.get(Booking, bk_id)
            bk_obj.driver_assigned_at = datetime.now(timezone.utc) - timedelta(seconds=900)
            db.session.commit()

        from app.tasks.transport_recovery import stall_recovery
        result = stall_recovery(stall_seconds=600, dry_run=True)
        assert bk_id in result["candidates"]
        assert bk_id not in result.get("recovered", [])
        assert _bk_field(app, bk_id, "status") == BookingStatus.ASSIGNED.value

        with app.app_context():
            AssignmentService.release(bk_id, BookingStatus.CANCELLED, actor=None, reason="dry_run_test")
        _delete(app, (Booking, bk_id), (DriverProfile, drv), (Vehicle, veh))


# =====================================================================
# Dispatch discovery + offer wiring tests (TH-3-D2 §20/§23)
# =====================================================================

def _make_matchable_driver(app, label="mch"):
    """Driver + owned vehicle + open DriverVehicleHistory + fresh canonical
    location, so the pool->ranker pipeline treats the driver as matchable
    (fresh canonical coordinates, ≥40 rank score)."""
    user_id, driver_id = _create_driver(app, f"m_{label}")
    veh_id = _create_vehicle(app, driver_id, f"m_{label}")
    with app.app_context():
        driver = db.session.get(DriverProfile, driver_id)
        driver.last_location = {
            'latitude': 0.3476,
            'longitude': 32.5825,
            'accuracy': 5.0,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        driver.location_updated_at = datetime.now(timezone.utc)
        history = DriverVehicleHistory(
            driver_id=driver_id,
            vehicle_id=veh_id,
            assignment_reason="test_dispatch",
            started_at=datetime.now(timezone.utc),
            ended_at=None,
        )
        db.session.add(history)
        db.session.commit()
        hist_id = history.id
    return user_id, driver_id, veh_id, hist_id


class TestDispatchDiscoveryAndOffer:
    def test_discover_and_offer_creates_offer_for_confirmed_unassigned(self, app, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)

        pax_id = _create_user(app, "paxDisp")
        _, drv, veh, hist = _make_matchable_driver(app, "d1")
        bk_id, bk_ref = _create_booking(app, pax_id, "disp")

        with app.app_context():
            assert db.session.get(Booking, bk_id).status == BookingStatus.CONFIRMED.value
            assert db.session.get(Booking, bk_id).assigned_driver_id is None

            from app.transport.services.matching_service import MatchingService
            outcome = MatchingService.discover_and_offer(bk_id)

        assert outcome["offers_created"] >= 1, outcome
        offer = OfferService.get_offer(bk_ref)
        assert offer is not None
        assert offer["driver_id"] == drv

        _delete(app, (DriverVehicleHistory, hist), (Booking, bk_id),
                (DriverProfile, drv), (Vehicle, veh))

    def test_dispatch_recovery_rediscovery_offers_confirmed_unassigned(self, app, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)

        pax_id = _create_user(app, "paxRec")
        _, drv, veh, hist = _make_matchable_driver(app, "d2")
        bk_id, bk_ref = _create_booking(app, pax_id, "rec")

        from app.tasks.transport_recovery import dispatch_recovery
        result = dispatch_recovery()

        assert result.get("rediscovered") >= 1, result
        assert result.get("offers_created") >= 1, result
        assert OfferService.get_offer(bk_ref) is not None

        _delete(app, (DriverVehicleHistory, hist), (Booking, bk_id),
                (DriverProfile, drv), (Vehicle, veh))


# =====================================================================
# FS-1: claim/release invalidate the booking read cache
# =====================================================================

class TestClaimInvalidatesBookingReadCache:
    """A claim must drop the cached get_booking dict so the next
    rides_show render reflects the ASSIGNED status, not CONFIRMED."""

    def test_claim_clears_booking_cache(self, app):
        pax_id = _create_user(app, "paxCache")
        _, drv, veh, hist = _make_matchable_driver(app, "c1")
        bk_id, bk_ref = _create_booking(app, pax_id, "cache")
        try:
            with app.app_context():
                from app.extensions import cache
                from app.transport.services import get_booking_service
                svc = get_booking_service()
                primed = svc.get_booking(bk_id)
                assert primed["status"] == BookingStatus.CONFIRMED.value
                assert cache.get(f"transport:booking:{bk_id}") is not None
                AssignmentService.claim(bk_ref, drv, veh, actor=None)
                assert cache.get(f"transport:booking:{bk_id}") is None
                fresh = svc.get_booking(bk_id)
                assert fresh["status"] == BookingStatus.ASSIGNED.value
                assert fresh["assigned_driver_id"] == drv
        finally:
            _delete(app, (DriverVehicleHistory, hist), (Booking, bk_id),
                    (DriverProfile, drv), (Vehicle, veh))

    def test_release_clears_booking_cache(self, app):
        pax_id = _create_user(app, "paxCacheRel")
        _, drv, veh, hist = _make_matchable_driver(app, "c2")
        bk_id, bk_ref = _create_booking(app, pax_id, "cacheRel")
        try:
            with app.app_context():
                from app.extensions import cache
                from app.transport.services import get_booking_service
                svc = get_booking_service()
                AssignmentService.claim(bk_ref, drv, veh, actor=None)
                assert svc.get_booking(bk_id)["status"] == (
                    BookingStatus.ASSIGNED.value)
                AssignmentService.release(bk_id, BookingStatus.COMPLETED,
                                          actor=None)
                assert cache.get(f"transport:booking:{bk_id}") is None
                assert svc.get_booking(bk_id)["status"] == (
                    BookingStatus.COMPLETED.value)
        finally:
            _delete(app, (DriverVehicleHistory, hist), (Booking, bk_id),
                    (DriverProfile, drv), (Vehicle, veh))
