"""
tests/test_transport_d5_execution_lifecycle.py
TH-3-D5: End-to-end transport EXECUTION lifecycle tests.

Proves the execution lifecycle contracts:

  E1  Driver trips endpoint advances ASSIGNED -> DRIVER_EN_ROUTE ->
      PICKUP_ARRIVED -> IN_PROGRESS -> COMPLETED (canonical release).
  E2  Admin status endpoint drives the parallel lifecycle, including
      cancellation at every stage and the DISPUTED latching path.
  E3  Resource safety after terminal states: driver/vehicle freed and
      reusable; stranded transitions refused.
  E4  Cancellation/advance races (both orderings, deterministic) plus one
      threaded HTTP accept-vs-cancel race.
  E5  Recovery-vs-progress races: stale-booking recovery never loots a
      trip that already advanced.
  E6  Moderator booking actions operate through the guarded release path
      (regression for the moderate_action resource-safe fix).

Conventions follow tests/test_transport_concurrent_claim.py: the
``threaded``-marked test is skipped by ``_isolate_db`` and self-cleans;
sequential HTTP tests rely on ``_isolate_db`` row-tracking cleanup.
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
from app.transport.services.assignment_service import AssignmentService


# =====================================================================
# Minimal FakeRedis (offer accept/decline need eval)
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
# Helpers — return integer IDs, not ORM objects
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


def _make_matchable_driver(app, label="mch"):
    """Driver + owned vehicle + open DriverVehicleHistory so
    ``current_vehicle`` resolves for the offer-accept endpoint."""
    user_id, driver_id = _create_driver(app, f"m_{label}")
    veh_id = _create_vehicle(app, driver_id, f"m_{label}")
    with app.app_context():
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


def _claim(app, booking_ref, driver_id, vehicle_id):
    with app.app_context():
        return AssignmentService.claim(booking_ref, driver_id, vehicle_id, actor=None)


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
    """Delete rows by (model_class, id) pairs (threaded tests self-clean)."""
    with app.app_context():
        for model, oid in ids_and_types:
            obj = db.session.get(model, oid)
            if obj:
                db.session.delete(obj)
        db.session.commit()


def _login_client(client, user):
    """Set Flask-Login session cookies on a client (conftest-equivalent)."""
    from app.identity.models.user import User
    app = client.application
    with app.app_context():
        if isinstance(user, int):
            user = db.session.get(User, user)
        merged = db.session.merge(user)
        uid = str(merged.public_id)
        db.session.rollback()
    with client.session_transaction() as sess:
        sess['_user_id'] = uid
        sess['_fresh'] = True


_TRIPS = "/api/transport/drivers/me/trips/{booking_id}/status"
_STATUS = "/api/transport/bookings/{booking_id}/status"
_OFFER = "/api/transport/drivers/me/offers/{reference}/accept"


def _trips(client, booking_id, action):
    return client.post(_TRIPS.format(booking_id=booking_id), json={"action": action})


_TRIPS_REF = "/api/transport/drivers/me/trips/{booking_reference}/status"


def _trips_ref(client, booking_reference, action):
    return client.post(_TRIPS_REF.format(booking_reference=booking_reference),
                       json={"action": action})


def _admin_status(client, booking_id, status_value, reason="admin_action"):
    return client.post(_STATUS.format(booking_id=booking_id),
                       json={"status": status_value, "reason": reason})


# =====================================================================
# E1 — Driver trips endpoint: full execution lifecycle
# =====================================================================

class TestDriverTripEndpoint:
    def test_full_trip_happy_path_and_canonical_completion(self, app, client):
        pax_id = _create_user(app, "paxE1")
        drv_user, drv = _create_driver(app, "dE1")
        veh = _create_vehicle(app, drv, "vE1")
        bk_id, bk_ref = _create_booking(app, pax_id, "E1")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)

        r = _trips(drv_client, bk_id, "en_route")
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["status"] == BookingStatus.DRIVER_EN_ROUTE.value
        assert _bk_field(app, bk_id, "status") == BookingStatus.DRIVER_EN_ROUTE.value
        assert _bk_field(app, bk_id, "driver_en_route_at") is not None

        r = _trips(drv_client, bk_id, "arrive")
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["status"] == BookingStatus.PICKUP_ARRIVED.value
        assert _bk_field(app, bk_id, "status") == BookingStatus.PICKUP_ARRIVED.value
        assert _bk_field(app, bk_id, "driver_arrived_at") is not None

        r = _trips(drv_client, bk_id, "start")
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["status"] == BookingStatus.IN_PROGRESS.value
        assert _bk_field(app, bk_id, "status") == BookingStatus.IN_PROGRESS.value

        r = _trips(drv_client, bk_id, "complete")
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert body["success"] is True
        assert body["data"]["status"] == BookingStatus.COMPLETED.value
        assert body["data"]["released"] is True

        assert _bk_field(app, bk_id, "status") == BookingStatus.COMPLETED.value
        assert _bk_field(app, bk_id, "assigned_driver_id") is None
        assert _bk_field(app, bk_id, "assigned_vehicle_id") is None
        assert _bk_field(app, bk_id, "completed_at") is not None
        assert _drv_field(app, drv, "is_available") is True
        assert _veh_field(app, veh, "is_available") is True

    def test_reference_keyed_full_lifecycle(self, app, client):
        """The reference-keyed variant (driver workspace Active Trip
        contract) runs the identical guarded lifecycle, no internal id."""
        pax_id = _create_user(app, "paxRF")
        drv_user, drv = _create_driver(app, "dRF")
        veh = _create_vehicle(app, drv, "vRF")
        bk_id, bk_ref = _create_booking(app, pax_id, "tRF")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)

        for action, expected in (
            ("en_route", BookingStatus.DRIVER_EN_ROUTE),
            ("arrive", BookingStatus.PICKUP_ARRIVED),
            ("start", BookingStatus.IN_PROGRESS),
            ("complete", BookingStatus.COMPLETED),
        ):
            r = _trips_ref(drv_client, bk_ref, action)
            assert r.status_code == 200, r.get_json()
            assert r.get_json()["data"]["status"] == expected.value
            assert _bk_field(app, bk_id, "status") == expected.value

        assert _bk_field(app, bk_id, "assigned_driver_id") is None
        assert _bk_field(app, bk_id, "completed_at") is not None
        assert _drv_field(app, drv, "is_available") is True

    def test_reference_keyed_unknown_and_foreign_driver(self, app, client):
        pax_id = _create_user(app, "paxRN")
        drv_user, drv = _create_driver(app, "dRN")
        veh = _create_vehicle(app, drv, "vRN")
        bk_id, bk_ref = _create_booking(app, pax_id, "tRN")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)

        r = _trips_ref(drv_client, "REF-DOES-NOT-EXIST", "en_route")
        assert r.status_code == 404

        other_user, _ = _create_driver(app, "dRN2")
        other_client = app.test_client()
        _login_client(other_client, other_user)
        r = _trips_ref(other_client, bk_ref, "en_route")
        assert r.status_code == 403
        assert _bk_field(app, bk_id, "status") == BookingStatus.ASSIGNED.value

    def test_wrong_driver_forbidden(self, app, client):
        pax_id = _create_user(app, "paxW")
        _, drv1 = _create_driver(app, "dW1")
        drv2_user, drv2 = _create_driver(app, "dW2")
        veh1 = _create_vehicle(app, drv1, "vW1")
        veh2 = _create_vehicle(app, drv2, "vW2")
        bk_id, bk_ref = _create_booking(app, pax_id, "tW")
        _claim(app, bk_ref, drv1, veh1)

        drv2_client = app.test_client()
        _login_client(drv2_client, drv2_user)
        r = _trips(drv2_client, bk_id, "en_route")
        assert r.status_code == 403
        assert _bk_field(app, bk_id, "status") == BookingStatus.ASSIGNED.value
        assert _bk_field(app, bk_id, "assigned_driver_id") == drv1

    def test_non_driver_authenticated_user_forbidden(self, app, test_user):
        pax_id = _create_user(app, "paxND")
        _, drv = _create_driver(app, "dND")
        veh = _create_vehicle(app, drv, "vND")
        bk_id, bk_ref = _create_booking(app, pax_id, "tND")
        _claim(app, bk_ref, drv, veh)

        user_client = app.test_client()
        _login_client(user_client, test_user)
        r = _trips(user_client, bk_id, "en_route")
        assert r.status_code == 403
        assert _bk_field(app, bk_id, "status") == BookingStatus.ASSIGNED.value

    def test_invalid_action_rejected(self, app, client, test_admin):
        pax_id = _create_user(app, "paxIA")
        drv_user, drv = _create_driver(app, "dIA")
        veh = _create_vehicle(app, drv, "vIA")
        bk_id, bk_ref = _create_booking(app, pax_id, "tIA")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        r = _trips(drv_client, bk_id, "teleport")
        assert r.status_code == 400
        assert _bk_field(app, bk_id, "status") == BookingStatus.ASSIGNED.value

    def test_wrong_state_conflict(self, app, client):
        pax_id = _create_user(app, "paxSt")
        drv_user, drv = _create_driver(app, "dSt")
        veh = _create_vehicle(app, drv, "vSt")
        bk_id, bk_ref = _create_booking(app, pax_id, "tSt")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        r = _trips(drv_client, bk_id, "start")  # start requires PICKUP_ARRIVED
        assert r.status_code == 409
        assert r.get_json()["code"] == "invalid_state"
        assert _bk_field(app, bk_id, "status") == BookingStatus.ASSIGNED.value

    def test_unassigned_booking_not_found(self, app, client):
        pax_id = _create_user(app, "paxNF")
        drv_user, drv = _create_driver(app, "dNF")
        veh = _create_vehicle(app, drv, "vNF")
        bk_id, bk_ref = _create_booking(app, pax_id, "tNF")

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        r = _trips(drv_client, bk_id, "en_route")
        assert r.status_code == 403  # no assignment -> not the assigned driver
        assert _bk_field(app, bk_id, "status") == BookingStatus.CONFIRMED.value


# =====================================================================
# E2 — Admin status endpoint: cancellation at every stage
# =====================================================================

class TestBookingCancellation:
    def test_cancel_assigned_booking_releases(self, app, admin_client):
        pax_id = _create_user(app, "paxCA")
        _, drv = _create_driver(app, "dCA")
        veh = _create_vehicle(app, drv, "vCA")
        bk_id, bk_ref = _create_booking(app, pax_id, "tCA")
        _claim(app, bk_ref, drv, veh)

        r = _admin_status(admin_client, bk_id, "cancelled", reason="passenger cancelled")
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert body["success"] is True
        assert body["release"]["released"] is True
        assert body["data"]["status"] == BookingStatus.CANCELLED.value
        assert _bk_field(app, bk_id, "status") == BookingStatus.CANCELLED.value
        assert _bk_field(app, bk_id, "assigned_driver_id") is None
        assert _bk_field(app, bk_id, "assigned_vehicle_id") is None
        assert _bk_field(app, bk_id, "cancelled_at") is not None
        assert _bk_field(app, bk_id, "cancellation_reason") == "passenger cancelled"
        assert _bk_field(app, bk_id, "cancellation_initiated_by") == "admin"
        assert _drv_field(app, drv, "is_available") is True
        assert _veh_field(app, veh, "is_available") is True

    def test_cancel_while_driver_en_route_releases(self, app, admin_client):
        pax_id = _create_user(app, "paxCE")
        drv_user, drv = _create_driver(app, "dCE")
        veh = _create_vehicle(app, drv, "vCE")
        bk_id, bk_ref = _create_booking(app, pax_id, "tCE")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        assert _trips(drv_client, bk_id, "en_route").status_code == 200

        r = _admin_status(admin_client, bk_id, "cancelled", reason="dispatch rfc")
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["release"]["released"] is True
        assert _bk_field(app, bk_id, "status") == BookingStatus.CANCELLED.value
        assert _bk_field(app, bk_id, "assigned_driver_id") is None
        assert _drv_field(app, drv, "is_available") is True

    def test_no_show_after_arrival_releases(self, app, admin_client):
        pax_id = _create_user(app, "paxNS")
        drv_user, drv = _create_driver(app, "dNS")
        veh = _create_vehicle(app, drv, "vNS")
        bk_id, bk_ref = _create_booking(app, pax_id, "tNS")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        assert _trips(drv_client, bk_id, "en_route").status_code == 200
        assert _trips(drv_client, bk_id, "arrive").status_code == 200

        r = _admin_status(admin_client, bk_id, "no_show", reason="pax no show")
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert body["release"]["released"] is True
        assert _bk_field(app, bk_id, "status") == BookingStatus.NO_SHOW.value
        assert _bk_field(app, bk_id, "assigned_driver_id") is None
        assert _drv_field(app, drv, "is_available") is True
        assert _veh_field(app, veh, "is_available") is True

    def test_dispute_latches_then_cancel_releases(self, app, admin_client):
        pax_id = _create_user(app, "paxDP")
        drv_user, drv = _create_driver(app, "dDP")
        veh = _create_vehicle(app, drv, "vDP")
        bk_id, bk_ref = _create_booking(app, pax_id, "tDP")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        _trips(drv_client, bk_id, "en_route")
        _trips(drv_client, bk_id, "arrive")
        assert _trips(drv_client, bk_id, "start").status_code == 200

        # DISPUTED is an ACTIVE ownership state: resources stay latched.
        r = _admin_status(admin_client, bk_id, "disputed", reason="fare dispute")
        assert r.status_code == 200, r.get_json()
        assert _bk_field(app, bk_id, "status") == BookingStatus.DISPUTED.value
        assert _bk_field(app, bk_id, "assigned_driver_id") == drv
        assert _drv_field(app, drv, "is_available") is False
        assert _veh_field(app, veh, "is_available") is False

        # Cancelling a DISPUTED booking closes it through the canonical release.
        r = _admin_status(admin_client, bk_id, "cancelled", reason="resolved")
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["release"]["released"] is True
        assert _bk_field(app, bk_id, "status") == BookingStatus.CANCELLED.value
        assert _bk_field(app, bk_id, "assigned_driver_id") is None
        assert _drv_field(app, drv, "is_available") is True
        assert _veh_field(app, veh, "is_available") is True

    def test_illegal_in_progress_to_cancelled_refused(self, app, admin_client):
        pax_id = _create_user(app, "paxIL")
        drv_user, drv = _create_driver(app, "dIL")
        veh = _create_vehicle(app, drv, "vIL")
        bk_id, bk_ref = _create_booking(app, pax_id, "tIL")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        _trips(drv_client, bk_id, "en_route")
        _trips(drv_client, bk_id, "arrive")
        assert _trips(drv_client, bk_id, "start").status_code == 200

        r = _admin_status(admin_client, bk_id, "cancelled", reason="mid trip")
        assert r.status_code == 422
        assert r.get_json()["success"] is False
        assert "allowed_transitions" in r.get_json()
        assert r.get_json()["allowed_transitions"] == [
            BookingStatus.COMPLETED.value, BookingStatus.DISPUTED.value,
        ]
        # resources remain latched (not lost, not stranded)
        assert _bk_field(app, bk_id, "status") == BookingStatus.IN_PROGRESS.value
        assert _bk_field(app, bk_id, "assigned_driver_id") == drv
        assert _drv_field(app, drv, "is_available") is False

    def test_repeat_cancel_after_terminal_refused_without_mutation(self, app, admin_client):
        pax_id = _create_user(app, "paxRC")
        _, drv = _create_driver(app, "dRC")
        veh = _create_vehicle(app, drv, "vRC")
        bk_id, bk_ref = _create_booking(app, pax_id, "tRC")
        _claim(app, bk_ref, drv, veh)

        r = _admin_status(admin_client, bk_id, "cancelled", reason="first")
        assert r.status_code == 200
        assert r.get_json()["release"]["released"] is True

        r = _admin_status(admin_client, bk_id, "cancelled", reason="again")
        assert r.status_code == 422  # terminal state: no outgoing transitions
        assert _bk_field(app, bk_id, "status") == BookingStatus.CANCELLED.value
        assert _bk_field(app, bk_id, "assigned_driver_id") is None
        assert _drv_field(app, drv, "is_available") is True


# =====================================================================
# E3 — Resource safety after terminal states
# =====================================================================

class TestResourceSafetyAfterTerminal:
    def test_driver_vehicle_reusable_after_completion(self, app, client):
        pax_id = _create_user(app, "paxRU")
        drv_user, drv = _create_driver(app, "dRU")
        veh = _create_vehicle(app, drv, "vRU")
        bkA_id, bkA_ref = _create_booking(app, pax_id, "tRUA")
        bkB_id, bkB_ref = _create_booking(app, pax_id, "tRUB")
        _claim(app, bkA_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        _trips(drv_client, bkA_id, "en_route")
        _trips(drv_client, bkA_id, "arrive")
        _trips(drv_client, bkA_id, "start")
        assert _trips(drv_client, bkA_id, "complete").status_code == 200

        # Same driver/vehicle can now be claimed onto a new booking.
        result = _claim(app, bkB_ref, drv, veh)
        assert result["status"] == BookingStatus.ASSIGNED.value
        assert result["booking_id"] == bkB_id

        with app.app_context():
            AssignmentService.release(bkB_id, BookingStatus.CANCELLED, actor=None, reason="test")

    def test_advance_after_cancel_refused(self, app, admin_client):
        pax_id = _create_user(app, "paxAC")
        drv_user, drv = _create_driver(app, "dAC")
        veh = _create_vehicle(app, drv, "vAC")
        bk_id, bk_ref = _create_booking(app, pax_id, "tAC")
        _claim(app, bk_ref, drv, veh)

        assert _admin_status(admin_client, bk_id, "cancelled", reason="rfc").status_code == 200

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        r = _trips(drv_client, bk_id, "en_route")
        assert r.status_code == 403  # assignment released; driver no longer holds it
        assert _bk_field(app, bk_id, "status") == BookingStatus.CANCELLED.value
        assert _drv_field(app, drv, "is_available") is True


# =====================================================================
# E4 — Cancellation/advance races (both orderings, deterministic)
# =====================================================================

class TestExecutionConcurrency:
    def test_cancel_before_en_route_blocks_en_route(self, app, admin_client):
        pax_id = _create_user(app, "paxC1")
        drv_user, drv = _create_driver(app, "dC1")
        veh = _create_vehicle(app, drv, "vC1")
        bk_id, bk_ref = _create_booking(app, pax_id, "tC1")
        _claim(app, bk_ref, drv, veh)

        assert _admin_status(admin_client, bk_id, "cancelled", reason="rfc").status_code == 200

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        r = _trips(drv_client, bk_id, "en_route")
        assert r.status_code == 403  # assignment already released
        assert _bk_field(app, bk_id, "status") == BookingStatus.CANCELLED.value

    def test_en_route_before_cancel_then_cancel_succeeds(self, app, admin_client):
        pax_id = _create_user(app, "paxC2")
        drv_user, drv = _create_driver(app, "dC2")
        veh = _create_vehicle(app, drv, "vC2")
        bk_id, bk_ref = _create_booking(app, pax_id, "tC2")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        assert _trips(drv_client, bk_id, "en_route").status_code == 200

        r = _admin_status(admin_client, bk_id, "cancelled", reason="rfc")
        assert r.status_code == 200
        assert r.get_json()["release"]["released"] is True
        assert _bk_field(app, bk_id, "status") == BookingStatus.CANCELLED.value
        assert _drv_field(app, drv, "is_available") is True

    def test_no_show_before_start_blocks_start(self, app, admin_client):
        pax_id = _create_user(app, "paxN1")
        drv_user, drv = _create_driver(app, "dN1")
        veh = _create_vehicle(app, drv, "vN1")
        bk_id, bk_ref = _create_booking(app, pax_id, "tN1")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        _trips(drv_client, bk_id, "en_route")
        _trips(drv_client, bk_id, "arrive")

        r = _admin_status(admin_client, bk_id, "no_show", reason="pax late")
        assert r.status_code == 200
        assert r.get_json()["release"]["released"] is True

        r = _trips(drv_client, bk_id, "start")
        assert r.status_code == 403  # released -> not the assigned driver anymore
        assert _bk_field(app, bk_id, "status") == BookingStatus.NO_SHOW.value
        assert _drv_field(app, drv, "is_available") is True

    def test_start_before_no_show_blocks_no_show(self, app, admin_client):
        pax_id = _create_user(app, "paxN2")
        drv_user, drv = _create_driver(app, "dN2")
        veh = _create_vehicle(app, drv, "vN2")
        bk_id, bk_ref = _create_booking(app, pax_id, "tN2")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        _trips(drv_client, bk_id, "en_route")
        _trips(drv_client, bk_id, "arrive")
        assert _trips(drv_client, bk_id, "start").status_code == 200

        r = _admin_status(admin_client, bk_id, "no_show", reason="late no show")
        assert r.status_code == 422  # IN_PROGRESS -> {COMPLETED, DISPUTED}
        assert _bk_field(app, bk_id, "status") == BookingStatus.IN_PROGRESS.value
        assert _drv_field(app, drv, "is_available") is False

        # cleanup: close in-progress trip
        assert _trips(drv_client, bk_id, "complete").status_code == 200

    def test_threaded_accept_vs_cancel_never_strands(self, app, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)

        pax_id = _create_user(app, "paxRace")
        drv_user, drv, veh, hist = _make_matchable_driver(app, "race")
        bk_id, bk_ref = _create_booking(app, pax_id, "tRace")

        from app.transport.services.offer_service import OfferService
        offer = OfferService.create_offer(bk_ref, driver_id=drv, vehicle_id=veh, ttl=300)
        assert offer["status"] == "offered"

        barrier = Barrier(2)
        outcomes = [None, None]

        def accept():
            c = app.test_client()
            _login_client(c, drv_user)
            barrier.wait(timeout=5)
            try:
                r = c.post(_OFFER.format(reference=bk_ref))
                outcomes[0] = (r.status_code, r.get_json())
            except Exception as e:  # pragma: no cover - defensive
                outcomes[0] = (None, str(e))

        def cancel():
            c = app.test_client()
            admin_user = _create_user_passthrough(app, "race_admin")
            _grant_owner(app, admin_user)
            _login_client(c, admin_user)
            barrier.wait(timeout=5)
            try:
                r = _admin_status(c, bk_id, "cancelled", reason="race")
                outcomes[1] = (r.status_code, r.get_json())
            except Exception as e:  # pragma: no cover - defensive
                outcomes[1] = (None, str(e))

        t0 = Thread(target=accept)
        t1 = Thread(target=cancel)
        t0.start(); t1.start()
        t0.join(timeout=15); t1.join(timeout=15)

        statuses = [o[0] for o in outcomes]
        assert all(s is not None and s < 500 for s in statuses), outcomes
        accept_ok = statuses[0] == 200
        cancel_ok = statuses[1] == 200
        assert accept_ok != cancel_ok, (
            "threaded accept/cancel must resolve to exactly one winner, got "
            f"accept={outcomes[0]} cancel={outcomes[1]}"
        )

        # Safety invariant: the booking is NEVER stranded.
        st = _bk_field(app, bk_id, "status")
        drv_bk = _bk_field(app, bk_id, "assigned_driver_id")
        if cancel_ok:
            assert st == BookingStatus.CANCELLED.value
            assert drv_bk is None
            assert _drv_field(app, drv, "is_available") is True
            assert _veh_field(app, veh, "is_available") is True
        else:
            assert st == BookingStatus.ASSIGNED.value
            assert drv_bk == drv
            assert _drv_field(app, drv, "is_available") is False
            assert _veh_field(app, veh, "is_available") is False

        with app.app_context():
            AssignmentService.release(bk_id, BookingStatus.CANCELLED, actor=None, reason="test_cleanup")
        _delete(app, (DriverVehicleHistory, hist), (Booking, bk_id),
                (DriverProfile, drv), (Vehicle, veh))


# =====================================================================
# E5 — Recovery-vs-progress races (stall recovery never loots trips)
# =====================================================================

class TestRecoveryVsProgress:
    def test_recovery_before_progress_cancels_stale_claim(self, app):
        pax_id = _create_user(app, "paxR1")
        drv_user, drv = _create_driver(app, "dR1")
        veh = _create_vehicle(app, drv, "vR1")
        bk_id, bk_ref = _create_booking(app, pax_id, "tR1")
        _claim(app, bk_ref, drv, veh)

        with app.app_context():
            bk_obj = db.session.get(Booking, bk_id)
            bk_obj.driver_assigned_at = datetime.now(timezone.utc) - timedelta(seconds=900)
            db.session.commit()

        from app.tasks.transport_recovery import stall_recovery
        result = stall_recovery(stall_seconds=600, dry_run=False)
        assert bk_id in result["recovered"]

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        r = _trips(drv_client, bk_id, "en_route")
        assert r.status_code == 403
        assert _bk_field(app, bk_id, "status") == BookingStatus.CANCELLED.value
        assert _drv_field(app, drv, "is_available") is True

    def test_progress_before_recovery_keeps_trip(self, app):
        pax_id = _create_user(app, "paxR2")
        drv_user, drv = _create_driver(app, "dR2")
        veh = _create_vehicle(app, drv, "vR2")
        bk_id, bk_ref = _create_booking(app, pax_id, "tR2")
        _claim(app, bk_ref, drv, veh)

        with app.app_context():
            bk_obj = db.session.get(Booking, bk_id)
            bk_obj.driver_assigned_at = datetime.now(timezone.utc) - timedelta(seconds=900)
            db.session.commit()

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        r = _trips(drv_client, bk_id, "en_route")
        assert r.status_code == 200

        from app.tasks.transport_recovery import stall_recovery
        result = stall_recovery(stall_seconds=600, dry_run=False)
        assert bk_id not in result["recovered"]
        assert _bk_field(app, bk_id, "status") == BookingStatus.DRIVER_EN_ROUTE.value
        assert _bk_field(app, bk_id, "assigned_driver_id") == drv
        assert _drv_field(app, drv, "is_available") is False

        # close the trip cleanly
        _trips(drv_client, bk_id, "arrive")
        _trips(drv_client, bk_id, "start")
        assert _trips(drv_client, bk_id, "complete").status_code == 200


# =====================================================================
# E6 — Moderator booking actions go through the guarded release path
# =====================================================================

def _create_user_passthrough(app, label):
    return _create_user(app, label)


def _grant_owner(app, user_id):
    with app.app_context():
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import get_or_create_role
        user = db.session.get(User, user_id)
        owner_role = get_or_create_role("owner", level=1)
        db.session.add(UserRole(user_id=user.id, role_id=owner_role.id))
        db.session.commit()


class TestModeratorBookingActions:
    def test_moderator_reject_assigned_booking_releases(self, app, client):
        pax_id = _create_user(app, "paxM1")
        _, drv = _create_driver(app, "dM1")
        veh = _create_vehicle(app, drv, "vM1")
        bk_id, bk_ref = _create_booking(app, pax_id, "tM1")
        _claim(app, bk_ref, drv, veh)

        moderate_user = _create_user(app, "modM1")
        _grant_owner(app, moderate_user)
        mod_client = app.test_client()
        _login_client(mod_client, moderate_user)

        r = mod_client.post(f"/transport/moderate/booking/{bk_id}/reject",
                            data={"reason": "violates dispatch contract"})
        assert r.status_code == 302
        assert _bk_field(app, bk_id, "status") == BookingStatus.CANCELLED.value
        assert _bk_field(app, bk_id, "assigned_driver_id") is None
        assert _bk_field(app, bk_id, "assigned_vehicle_id") is None
        assert _bk_field(app, bk_id, "cancelled_at") is not None
        assert _bk_field(app, bk_id, "cancellation_reason") == "violates dispatch contract"
        assert _bk_field(app, bk_id, "cancellation_initiated_by") == "moderator"
        assert _drv_field(app, drv, "is_available") is True
        assert _veh_field(app, veh, "is_available") is True

    def test_moderator_reject_in_progress_blocked(self, app, client):
        pax_id = _create_user(app, "paxM2")
        drv_user, drv = _create_driver(app, "dM2")
        veh = _create_vehicle(app, drv, "vM2")
        bk_id, bk_ref = _create_booking(app, pax_id, "tM2")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        _trips(drv_client, bk_id, "en_route")
        _trips(drv_client, bk_id, "arrive")
        assert _trips(drv_client, bk_id, "start").status_code == 200

        moderate_user = _create_user(app, "modM2")
        _grant_owner(app, moderate_user)
        mod_client = app.test_client()
        _login_client(mod_client, moderate_user)
        r = mod_client.post(f"/transport/moderate/booking/{bk_id}/reject",
                            data={"reason": "admin whim"})
        assert r.status_code == 302
        # formally refused: still IN_PROGRESS, resources still held
        assert _bk_field(app, bk_id, "status") == BookingStatus.IN_PROGRESS.value
        assert _bk_field(app, bk_id, "assigned_driver_id") == drv
        assert _drv_field(app, drv, "is_available") is False

        _trips(drv_client, bk_id, "complete")

    def test_moderator_reject_completed_blocked(self, app, client):
        pax_id = _create_user(app, "paxM3")
        drv_user, drv = _create_driver(app, "dM3")
        veh = _create_vehicle(app, drv, "vM3")
        bk_id, bk_ref = _create_booking(app, pax_id, "tM3")
        _claim(app, bk_ref, drv, veh)

        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        _trips(drv_client, bk_id, "en_route")
        _trips(drv_client, bk_id, "arrive")
        _trips(drv_client, bk_id, "start")
        assert _trips(drv_client, bk_id, "complete").status_code == 200

        moderate_user = _create_user(app, "modM3")
        _grant_owner(app, moderate_user)
        mod_client = app.test_client()
        _login_client(mod_client, moderate_user)
        r = mod_client.post(f"/transport/moderate/booking/{bk_id}/reject",
                            data={"reason": "late rejection"})
        assert r.status_code == 302
        assert _bk_field(app, bk_id, "status") == BookingStatus.COMPLETED.value
        assert _drv_field(app, drv, "is_available") is True

    def test_moderator_approve_guards_state(self, app, client):
        pax_id = _create_user(app, "paxM4")
        drv_user, drv = _create_driver(app, "dM4")
        veh = _create_vehicle(app, drv, "vM4")
        bk_id, bk_ref = _create_booking(app, pax_id, "tM4",
                                        status=BookingStatus.PENDING_PAYMENT)

        moderate_user = _create_user(app, "modM4")
        _grant_owner(app, moderate_user)
        mod_client = app.test_client()
        _login_client(mod_client, moderate_user)

        r = mod_client.post(f"/transport/moderate/booking/{bk_id}/approve")
        assert r.status_code == 302
        assert _bk_field(app, bk_id, "status") == BookingStatus.CONFIRMED.value
        assert _bk_field(app, bk_id, "confirmed_at") is not None

        # Re-approving an already-confirmed booking is a guarded no-op.
        r = mod_client.post(f"/transport/moderate/booking/{bk_id}/approve")
        assert r.status_code == 302
        assert _bk_field(app, bk_id, "status") == BookingStatus.CONFIRMED.value

        # Approving an executing booking is refused (would be a strand risk).
        _claim(app, bk_ref, drv, veh)
        drv_client = app.test_client()
        _login_client(drv_client, drv_user)
        _trips(drv_client, bk_id, "en_route")
        r = mod_client.post(f"/transport/moderate/booking/{bk_id}/approve")
        assert r.status_code == 302
        assert _bk_field(app, bk_id, "status") == BookingStatus.DRIVER_EN_ROUTE.value

        # cleanup: closed via the owner/admin status endpoint
        r = mod_client.post(_STATUS.format(booking_id=bk_id),
                            json={"status": "cancelled", "reason": "test cleanup"})
        assert r.status_code == 200
        assert _bk_field(app, bk_id, "status") == BookingStatus.CANCELLED.value

    def test_moderator_reject_requires_reason(self, app, client):
        pax_id = _create_user(app, "paxM5")
        _, drv = _create_driver(app, "dM5")
        veh = _create_vehicle(app, drv, "vM5")
        bk_id, bk_ref = _create_booking(app, pax_id, "tM5")
        _claim(app, bk_ref, drv, veh)

        moderate_user = _create_user(app, "modM5")
        _grant_owner(app, moderate_user)
        mod_client = app.test_client()
        _login_client(mod_client, moderate_user)
        r = mod_client.post(f"/transport/moderate/booking/{bk_id}/reject",
                            data={"reason": ""})
        assert r.status_code == 302
        assert _bk_field(app, bk_id, "status") == BookingStatus.ASSIGNED.value
        assert _bk_field(app, bk_id, "assigned_driver_id") == drv
        assert _drv_field(app, drv, "is_available") is False