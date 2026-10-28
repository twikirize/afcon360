"""
tests/test_transport_booking_route_path.py
REAL RIDE TRANSACTION PATH — route-level proof.

Closes the final evidence gap for the rider journey:

  LOCATIONS -> QUOTE -> RIDER ACCEPTANCE -> REQUEST/SEARCH
    -> REQUEST (POST /transport/book; no Booking row before acceptance)
    -> durable OfferAttempt -> ACCEPT -> atomic Booking + assignment

The chain was previously proven only at service level (fare_engine pins
vehicle_class persistence; concurrent_claim / d2_evidence prove
discover/offer/claim; the front-page suite and browser verification proved
the auth and KYC gates). No test created a booking through the ACTUAL
``POST /transport/book`` route with an authorized rider and then ran that
route-created booking through dispatch to a real assignment.

Test 1: a tier-1 rider (phone verified only, no identity verification)
         POSTing ``/transport/book`` is redirected to the KYC upgrade page —
         the same gate observed in-browser, now pinned at route level.

Test 2: a tier-3 rider POSTs the bolt-sheet form; a durable RideRequest and
         SearchCycle exist, with no Booking before driver acceptance. The
         seeded matchable driver accepts; the same public reference then
         resolves to a Booking atomically assigned to that driver and vehicle,
         with payment still pending.
"""
import uuid

import pytest
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.identity.models.user import User
from app.transport.models import (
    Booking,
    BookingPayment,
    BookingStatus,
    ComplianceStatus,
    Currency,
    DriverProfile,
    DriverVehicleHistory,
    Vehicle,
    VehicleClass,
    PaymentStatus,
    RideRequest,
    SearchCycle,
    OfferAttempt,
)


# =====================================================================
# FakeRedis — offer_service needs eval for the accept/decline Lua CAS
# =====================================================================

class _FakeRedis:
    """In-memory Redis stand-in, identical contract to concurrent_claim."""

    def __init__(self):
        self._hash = {}
        self._set = {}

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
        if self.hget(offer_key, "status") != expected:
            return 0
        if self.hget(offer_key, "driver_id") != driver_id_str:
            return 0
        self.hset(offer_key, mapping={"status": target})
        self.srem(driver_key, booking_ref)
        self.srem(index_key, driver_id_str)
        return 1

    def _eval_decline(self, script_args, keys_args):
        driver_id_str, booking_ref = script_args
        offer_key, driver_key, index_key = keys_args
        if self.hget(offer_key, "driver_id") != driver_id_str:
            return 0
        self.srem(driver_key, booking_ref)
        self.srem(index_key, driver_id_str)
        self.delete(offer_key)
        return 1


# =====================================================================
# Bolt-sheet form payload (mirrors templates/transport/home.html)
# =====================================================================

def _bolt_form(app, pickup_time: str) -> dict:
    form = {
        "service_type": "on_demand",
        "provider_type": "individual_driver",
        "passenger_count": "1",
        "luggage_count": "0",
        "currency": "USD",
        "pickup_time": pickup_time,
        "payment_method": "cash",
        "idempotency_key": "test-%s" % uuid.uuid4().hex,
        "booking_mode": "instant",
        "vehicle_class": "comfort",
        "pickup_location": "Kampala Centre",
        "dropoff_location": "Nile Independence Stadium",
        "pickup_latitude": "0.3136",
        "pickup_longitude": "32.5811",
        "dropoff_latitude": "0.3161",
        "dropoff_longitude": "32.6056",
    }
    with app.app_context():
        from app.transport.services.booking_service import _measured_distance_km
        from app.transport.services.fare_service import calculate_estimate
        from app.transport.services.fare_quote_service import (
            issue_fare_quote, money_amount,
        )

        pickup = {
            "latitude": float(form["pickup_latitude"]),
            "longitude": float(form["pickup_longitude"]),
            "address": form["pickup_location"],
        }
        dropoff = {
            "latitude": float(form["dropoff_latitude"]),
            "longitude": float(form["dropoff_longitude"]),
            "address": form["dropoff_location"],
        }
        quoted_at = datetime.now().replace(microsecond=0)
        distance_km = _measured_distance_km(pickup, dropoff)
        estimate = calculate_estimate(
            service_type=form["service_type"],
            vehicle_class=form["vehicle_class"],
            distance_km=distance_km,
            at=quoted_at,
        )
        currency = str(estimate.get("currency") or "USD").upper()
        amount = money_amount(estimate["total"])
        form["currency"] = currency
        form["confirmed_fare_amount"] = format(amount, ".2f")
        form["fare_quote_token"] = issue_fare_quote(
            service_type=form["service_type"],
            vehicle_class=form["vehicle_class"],
            currency=currency,
            amount=amount,
            fare_version=estimate.get("version"),
            pickup=pickup,
            dropoff=dropoff,
            distance_km=distance_km,
            quoted_at=quoted_at,
        )
    return form


# =====================================================================
# Rider / driver seeding (mirrors driver-workspace + concurrent_claim)
# =====================================================================

def _promote_user_to_tier3(app, user_id: int):
    """Canonical tier-3 state: phone verified + verified identity
    verification covering national_id/biometric (proves the require_kyc_tier
    gate is satisfiable through the real calculate_kyc_tier authority)."""
    from app.identity.individuals.individual_verification import (
        IndividualVerification,
    )

    with app.app_context():
        real_user = db.session.get(User, user_id)
        real_user.phone_verified = True
        real_user.phone_verified_at = datetime.now(timezone.utc)
        if not real_user.phone:
            real_user.phone = f"+2567{uuid.uuid4().hex[:7]}"
        db.session.add(
            IndividualVerification(
                user_id=user_id,
                status="verified",
                scope={
                    "identity": True,
                    "address": True,
                    "national_id": True,
                    "biometric": True,
                },
            )
        )
        db.session.commit()

    from app.auth.kyc_compliance import calculate_kyc_tier
    with app.app_context():
        info = calculate_kyc_tier(user_id)
        assert info["tier"] >= 2, f"rider did not reach tier 2: {info}"


def _make_matchable_driver(app, label="rt"):
    """Fully eligible driver: approved/online driver + active comfort vehicle
    + open DriverVehicleHistory + fresh canonical location (rank >= 40)."""
    from app.transport.services.matching_service import MatchingService
    from app.transport.services.offer_service import OfferService

    owner_user_id = _create_user(app, f"drv_{label}")
    with app.app_context():
        dp = DriverProfile(
            user_id=owner_user_id,
            driver_code=f"RT-{label}-{uuid.uuid4().hex[:6].upper()}",
            verification_tier="platform_verified",
            compliance_status=ComplianceStatus.APPROVED,
            is_active=True,
            is_online=True,
            is_available=True,
            max_passenger_capacity=4,
            vehicle_classes=["comfort"],
        )
        db.session.add(dp)
        db.session.commit()
        driver_id = dp.id

        veh = Vehicle(
            owner_type="driver",
            owner_id=driver_id,
            license_plate=f"UG-{label}-{uuid.uuid4().hex[:4].upper()}",
            make="Toyota",
            model="Corolla",
            year=2022,
            vehicle_type="sedan",
            vehicle_class=VehicleClass.COMFORT,
            passenger_capacity=4,
            status="active",
            is_available=True,
        )
        db.session.add(veh)
        db.session.commit()
        vehicle_id = veh.id

        driver = db.session.get(DriverProfile, driver_id)
        driver.last_location = {
            "latitude": 0.3476,
            "longitude": 32.5825,
            "accuracy": 5.0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        driver.location_updated_at = datetime.now(timezone.utc)
        history = DriverVehicleHistory(
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            assignment_reason="test_route_path",
            started_at=datetime.now(timezone.utc),
            ended_at=None,
        )
        db.session.add(history)
        db.session.commit()
        hist_id = history.id
    return owner_user_id, driver_id, vehicle_id, hist_id


def _create_user(app, label="user"):
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        u = User(
            username=f"{label}_{uid}",
            email=f"{label}_{uid}@test.example.com",
            is_verified=True,
            is_active=True,
        )
        u.set_password("TestPass123!")
        db.session.add(u)
        db.session.commit()
        return u.id


def _new_pickup_time():
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


# =====================================================================
# 1. KYC gate on the ACTUAL route (tier-1 rider is blocked)
# =====================================================================

class TestKycGateOnBookRoute:
    def test_tier1_rider_redirected_to_kyc_upgrade(self, app, authenticated_client, test_user):
        # test_user starts without phone verification and without any
        # IndividualVerification -> guaranteed tier < 2.
        from app.auth.kyc_compliance import calculate_kyc_tier
        with app.app_context():
            merged = db.session.merge(test_user)  # reattach expired fixture row
            rider_id = merged.id
            info = calculate_kyc_tier(rider_id)
        assert info["tier"] < 2, "fixture user unexpectedly reached tier 2+"

        resp = authenticated_client.post(
            "/transport/book",
            data=_bolt_form(app, _new_pickup_time()),
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302), (
            f"expected KYC redirect, got {resp.status_code}"
        )
        assert "/kyc/upgrade" in resp.headers.get("Location", ""), (
            f"must redirect to KYC upgrade, got {resp.headers.get('Location')}"
        )


class TestRequestFirstStaleVehicleOffer:
    def test_offer_cannot_claim_vehicle_after_driver_switches_away(
        self, app, authenticated_client, test_user
    ):
        from app.transport.models import DriverVehicleHistory, RideRequest, SearchCycle, OfferAttempt
        from app.transport.services.ride_request_dispatch_service import (
            RideRequestDispatchService, RideRequestDispatchError,
        )

        with app.app_context():
            rider = db.session.merge(test_user)
            rider_id = rider.id
            _promote_user_to_tier3(app, rider_id)
        _, driver_id, vehicle_id, history_id = _make_matchable_driver(app, "stalevehicle")

        response = authenticated_client.post(
            "/transport/book",
            data=_bolt_form(app, _new_pickup_time()),
            follow_redirects=False,
        )
        assert response.status_code in (301, 302), response.get_data(as_text=True)
        reference = response.headers["Location"].rstrip("/").rsplit("/", 1)[1]

        with app.app_context():
            request_row = RideRequest.query.filter_by(public_id=reference).one()
            cycle = SearchCycle.query.filter_by(
                ride_request_id=request_row.id, cycle_number=1
            ).one()
            offer = OfferAttempt.query.filter_by(
                cycle_id=cycle.id, driver_id=driver_id, vehicle_id=vehicle_id,
                status="offered",
            ).one()
            history = db.session.get(DriverVehicleHistory, history_id)
            history.ended_at = datetime.now(timezone.utc)
            db.session.commit()
            offer_id = offer.id

        with pytest.raises(RideRequestDispatchError) as exc:
            RideRequestDispatchService.accept_offer(
                reference, driver_id, vehicle_id, actor=None
            )
        assert exc.value.code == "vehicle_assignment_changed"

        with app.app_context():
            request_row = RideRequest.query.filter_by(public_id=reference).one()
            cycle = SearchCycle.query.filter_by(
                ride_request_id=request_row.id, cycle_number=1
            ).one()
            offer = db.session.get(OfferAttempt, offer_id)
            assert request_row.status == "searching"
            assert cycle.status == "expired"
            assert offer.status == "claim_failed"
            assert Booking.query.filter_by(booking_reference=reference).one_or_none() is None


class TestExplicitPaymentChoiceOnBookRoute:
    def test_missing_payment_method_does_not_create_a_ride_request(
        self, app, authenticated_client, test_user
    ):
        with app.app_context():
            rider = db.session.merge(test_user)
            rider_id = rider.id
            _promote_user_to_tier3(app, rider_id)

        form = _bolt_form(app, _new_pickup_time())
        form.pop("payment_method", None)
        response = authenticated_client.post(
            "/transport/book", data=form, follow_redirects=False
        )
        assert response.status_code in (301, 302)
        with app.app_context():
            assert RideRequest.query.filter_by(user_id=rider_id, is_deleted=False).count() == 0
            assert Booking.query.filter_by(user_id=rider_id, is_deleted=False).count() == 0


    def test_missing_signed_fare_quote_does_not_create_request_or_search(
        self, app, authenticated_client, test_user
    ):
        with app.app_context():
            rider = db.session.merge(test_user)
            rider_id = rider.id
            _promote_user_to_tier3(app, rider_id)

        with app.app_context():
            before_cycles = SearchCycle.query.count()
        form = _bolt_form(app, _new_pickup_time())
        form.pop("fare_quote_token", None)
        response = authenticated_client.post(
            "/transport/book", data=form, follow_redirects=False
        )
        assert response.status_code in (301, 302)
        with app.app_context():
            assert RideRequest.query.filter_by(
                user_id=rider_id, is_deleted=False
            ).count() == 0
            assert Booking.query.filter_by(
                user_id=rider_id, is_deleted=False
            ).count() == 0
            assert SearchCycle.query.count() == before_cycles

    def test_changed_confirmed_fare_does_not_create_request(
        self, app, authenticated_client, test_user
    ):
        with app.app_context():
            rider = db.session.merge(test_user)
            rider_id = rider.id
            _promote_user_to_tier3(app, rider_id)

        with app.app_context():
            before_cycles = SearchCycle.query.count()
        form = _bolt_form(app, _new_pickup_time())
        from decimal import Decimal
        form["confirmed_fare_amount"] = format(
            Decimal(form["confirmed_fare_amount"]) + Decimal("1.00"), ".2f"
        )
        response = authenticated_client.post(
            "/transport/book", data=form, follow_redirects=False
        )
        assert response.status_code in (301, 302)
        with app.app_context():
            assert RideRequest.query.filter_by(
                user_id=rider_id, is_deleted=False
            ).count() == 0
            assert Booking.query.filter_by(
                user_id=rider_id, is_deleted=False
            ).count() == 0
            assert SearchCycle.query.count() == before_cycles


# =====================================================================
# 2. Full REAL RIDE TRANSACTION PATH through POST /transport/book
# =====================================================================

class TestRealRideTransactionPath:
    def test_route_tracks_request_then_converts_after_driver_acceptance(
        self, app, authenticated_client, test_user, monkeypatch
    ):
        with app.app_context():
            merged = db.session.merge(test_user)
            rider_id = merged.id
            _promote_user_to_tier3(app, rider_id)

        _, driver_id, vehicle_id, _ = _make_matchable_driver(app, "requestfirst")

        resp = authenticated_client.post(
            "/transport/book",
            data=_bolt_form(app, _new_pickup_time()),
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302), (
            f"expected ride-request redirect, got {resp.status_code}"
        )
        location = resp.headers.get("Location", "")
        assert "/transport/rides/" in location, location
        reference = location.rstrip("/").rsplit("/", 1)[1]
        assert reference

        # Initial commitment is a tracking request, not a confirmed Booking.
        with app.app_context():
            request_row = RideRequest.query.filter_by(
                public_id=reference, user_id=rider_id, is_deleted=False
            ).one()
            cycle = SearchCycle.query.filter_by(
                ride_request_id=request_row.id, cycle_number=1, is_deleted=False
            ).one()
            assert request_row.status == "searching"
            assert cycle.status == "searching"
            assert request_row.payment_method == "cash"
            assert Booking.query.filter_by(booking_reference=reference).one_or_none() is None
            attempt = OfferAttempt.query.filter_by(
                cycle_id=cycle.id, driver_id=driver_id, status="offered"
            ).one()
            assert attempt.vehicle_id == vehicle_id

        # Acceptance is the only point that creates the Booking. The request,
        # cycle, Booking, and assigned driver+vehicle transition together.
        from app.transport.services.ride_request_dispatch_service import (
            RideRequestDispatchService,
        )
        result = RideRequestDispatchService.accept_offer(
            reference, driver_id, vehicle_id, actor=None
        )
        assert result["status"] == BookingStatus.ASSIGNED.value

        with app.app_context():
            request_row = RideRequest.query.filter_by(public_id=reference).one()
            cycle = SearchCycle.query.filter_by(
                ride_request_id=request_row.id, cycle_number=1
            ).one()
            booking = Booking.query.filter_by(
                booking_reference=reference, ride_request_id=request_row.id
            ).one()
            assert request_row.status == "converted"
            assert request_row.converted_at is not None
            assert cycle.status == "completed"
            assert booking.status == BookingStatus.ASSIGNED.value
            assert booking.assigned_driver_id == driver_id
            assert booking.assigned_vehicle_id == vehicle_id
            assert booking.payment_method == "cash"
            assert booking.payment_status == PaymentStatus.PENDING.value
            payment_row = BookingPayment.query.filter_by(
                booking_id=booking.id
            ).one()
            assert payment_row.payment_status == PaymentStatus.PENDING
            assert payment_row.payment_method == "cash"
            assert payment_row.amount > 0
            assert payment_row.payment_reference
            assert booking.booking_metadata["payment_timing"] == "pay_on_completion"
            assert booking.confirmed_at is not None
            assert booking.driver_assigned_at is not None

        # Rider-facing history must distinguish when the request was received
        # from when a driver accepted it; booking-row creation happens at accept.
        trip_page = authenticated_client.get(location)
        assert trip_page.status_code == 200, trip_page.get_data(as_text=True)
        trip_html = trip_page.get_data(as_text=True)
        assert "Ride Request Received" in trip_html
        assert "Driver Accepted" in trip_html
