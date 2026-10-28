"""BOOKING-LIFECYCLE-REQUEST-CREATE (Stage 3B, Phase 2A).

Creation + idempotency + no-premature-Booking proofs for POST
/api/transport/ride-requests. Self-contained helpers (no cross-module
test imports); shared fixtures (app/client/db_session) untouched.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db

pytestmark = pytest.mark.usefixtures("db_session")

URL = "/api/transport/ride-requests"

PICKUP = {"latitude": 0.3136, "longitude": 32.5811, "address": "Kampala Centre"}
DROPOFF = {"latitude": 0.3476, "longitude": 32.5825, "address": "Stadium Gate"}


def _payload(app, **overrides):
    """A real signed server quote for direct service/API contract tests."""
    body = {
        "idempotency_key": "req-%s" % uuid.uuid4().hex,
        "pickup": dict(PICKUP),
        "dropoff": dict(DROPOFF),
        "pickup_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "service_type": "on_demand",
        "vehicle_class": "comfort",
        "passenger_count": 1,
        "payment_method": "cash",
        "currency": "USD",
    }
    body.update(overrides)
    with app.app_context():
        from app.transport.services.booking_service import _measured_distance_km
        from app.transport.services.fare_service import calculate_estimate
        from app.transport.services.fare_quote_service import (
            issue_fare_quote, money_amount,
        )

        quoted_at = datetime.now().replace(microsecond=0)
        distance_km = _measured_distance_km(body["pickup"], body["dropoff"])
        estimate = calculate_estimate(
            service_type=body["service_type"],
            vehicle_class=body["vehicle_class"],
            distance_km=distance_km,
            at=quoted_at,
        )
        currency = str(estimate.get("currency") or "USD").upper()
        amount = money_amount(estimate["total"])
        body["currency"] = currency
        body["confirmed_fare_amount"] = format(amount, ".2f")
        body["fare_quote_token"] = issue_fare_quote(
            service_type=body["service_type"],
            vehicle_class=body["vehicle_class"],
            currency=currency,
            amount=amount,
            fare_version=estimate.get("version"),
            pickup=body["pickup"],
            dropoff=body["dropoff"],
            distance_km=distance_km,
            quoted_at=quoted_at,
        )
    return body


def _seed_rider(app, label="rrc"):
    from app.identity.models.user import User

    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username="%s_%s" % (label, uid),
                    email="%s_%s@test.example.com" % (label, uid),
                    is_active=True, is_verified=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.commit()
        return user.id


def _promote_to_tier2(app, user_id):
    """Canonical tier-2 state through the real KYC authority (no mocks)."""
    from app.identity.individuals.individual_verification import (
        IndividualVerification,
    )
    from app.identity.models.user import User

    with app.app_context():
        real = db.session.get(User, user_id)
        real.phone_verified = True
        real.phone_verified_at = datetime.now(timezone.utc)
        if not real.phone:
            real.phone = "+2567%s" % uuid.uuid4().hex[:7]
        db.session.add(IndividualVerification(
            user_id=user_id, status="verified",
            scope={"identity": True, "address": True,
                   "national_id": True, "biometric": True}))
        db.session.commit()
    from app.auth.kyc_compliance import calculate_kyc_tier
    with app.app_context():
        info = calculate_kyc_tier(user_id)
        assert info["tier"] >= 2, "rider did not reach tier 2: %s" % info


def _login_as(app, client, user_id):
    """Session login following tests/conftest.py::_login_client exactly.

    The public id is read while the instance is attached and committed
    state is rolled back BEFORE opening session_transaction: reading
    expired ORM attributes afterwards trips the app's request-teardown
    session lifecycle (DetachedInstanceError).
    """
    from app.identity.models.user import User

    with app.app_context():
        merged = db.session.merge(db.session.get(User, user_id))
        uid = str(merged.public_id)
        db.session.rollback()
    with client.session_transaction() as sess:
        sess["_user_id"] = uid
        sess["_fresh"] = True
    return client


def _counts(app, user_id):
    from app.transport.models import Booking, RideRequest, SearchCycle

    with app.app_context():
        return (
            RideRequest.query.filter_by(user_id=user_id, is_deleted=False).count(),
            SearchCycle.query.join(
                RideRequest,
                SearchCycle.ride_request_id == RideRequest.id).filter(
                    RideRequest.user_id == user_id).count(),
            Booking.query.filter_by(user_id=user_id, is_deleted=False).count(),
        )


class TestRequestCreate:
    def test_valid_request_creates_one_request_and_one_cycle(self, app, client):
        rider_id = _seed_rider(app)
        _promote_to_tier2(app, rider_id)
        _login_as(app, client, rider_id)

        resp = client.post(URL, json=_payload(app, ))
        assert resp.status_code == 201, resp.get_data(as_text=True)
        data = resp.get_json()["data"]
        assert data["request_id"] and len(data["request_id"]) >= 16
        assert data["status"] == "searching"
        assert data["cycle"]["number"] == 1
        assert data["cycle"]["status"] == "searching"
        assert data["cycle"]["deadline"]
        assert data["fare_estimate"]["amount"] > 0
        # Safe serialization: opaque id only.
        assert set(data) <= {"request_id", "status", "cycle", "service_type",
                             "vehicle_class", "passenger_count", "pickup_time",
                             "fare_estimate", "payment_method", "created_at"}
        assert set(data["cycle"]) <= {"number", "status", "started_at", "deadline"}
        blob = resp.get_data(as_text=True).lower()
        assert "booking_reference" not in blob
        assert "assigned_driver" not in blob
        assert "user_id" not in blob.replace("request_id", "")

        requests, cycles, bookings = _counts(app, rider_id)
        assert (requests, cycles, bookings) == (1, 1, 0)

    def test_zero_booking_rows_and_no_reference(self, app, client):
        from app.transport.models import Booking

        rider_id = _seed_rider(app)
        _promote_to_tier2(app, rider_id)
        with app.app_context():
            before = Booking.query.count()
        _login_as(app, client, rider_id)
        body = _payload(app, )
        assert client.post(URL, json=body).status_code == 201
        assert client.post(URL, json=body).status_code == 200  # replay
        with app.app_context():
            assert Booking.query.count() == before
            assert Booking.query.filter_by(user_id=rider_id).count() == 0

    def test_identical_replay_resolves_to_same_request_and_cycle(self, app, client):
        rider_id = _seed_rider(app)
        _promote_to_tier2(app, rider_id)
        _login_as(app, client, rider_id)

        body = _payload(app, )
        first = client.post(URL, json=body).get_json()
        second = client.post(URL, json=body)
        assert second.status_code == 200, second.get_data(as_text=True)
        assert second.get_json()["replayed"] is True
        assert second.get_json()["data"]["request_id"] == first["data"]["request_id"]
        assert second.get_json()["data"]["cycle"] == first["data"]["cycle"]
        requests, cycles, bookings = _counts(app, rider_id)
        assert (requests, cycles, bookings) == (1, 1, 0)

    def test_key_reuse_with_different_trip_is_conflict_without_mutation(self, app, client):
        from app.transport.models import RideRequest

        rider_id = _seed_rider(app)
        _promote_to_tier2(app, rider_id)
        _login_as(app, client, rider_id)

        key = "req-%s" % uuid.uuid4().hex
        assert client.post(URL, json=_payload(app, idempotency_key=key)).status_code == 201
        conflict = client.post(URL, json=_payload(app, 
            idempotency_key=key,
            dropoff={"latitude": 0.4000, "longitude": 32.6500}))
        assert conflict.status_code == 409, conflict.get_data(as_text=True)
        assert conflict.get_json()["code"] == "idempotency_conflict"

        # Original untouched: same snapshot, still one request + one cycle.
        with app.app_context():
            stored = RideRequest.query.filter_by(
                user_id=rider_id, idempotency_key=key, is_deleted=False).one()
            assert stored.dropoff_location["latitude"] == DROPOFF["latitude"]
        requests, cycles, bookings = _counts(app, rider_id)
        assert (requests, cycles, bookings) == (1, 1, 0)


class TestRollbackAfterPartialFlush:
    def test_cycle_failure_rolls_back_flushed_request(self, app, client):
        """Fault-injection rollback proof: the RideRequest flush succeeds,
        then the SearchCycle insert fails; the real service error path must
        roll back so neither partial row survives and no Booking appears.
        """
        from sqlalchemy import event
        from sqlalchemy.exc import SQLAlchemyError

        from app.transport.models import Booking, RideRequest, SearchCycle

        rider_id = _seed_rider(app)
        _promote_to_tier2(app, rider_id)
        _login_as(app, client, rider_id)

        key = "req-%s" % uuid.uuid4().hex
        body = _payload(app, idempotency_key=key)
        expected_cycle_key = "%s:1" % key
        seen = {"fired": False, "ride_request_id": None}

        def _fail_cycle(mapper, connection, target):
            # Strict key gate: fires only for this test's SearchCycle insert.
            if target.cycle_key != expected_cycle_key:
                return
            # ride_request.id assigned here proves the L391 flush ran first.
            seen["fired"] = True
            seen["ride_request_id"] = target.ride_request_id
            raise SQLAlchemyError(
                "injected SearchCycle failure (rollback proof)")

        with app.app_context():
            bookings_before = Booking.query.count()
        requests_before, cycles_before, _ = _counts(app, rider_id)

        event.listen(SearchCycle, "before_insert", _fail_cycle)
        try:
            resp = client.post(URL, json=body)
        finally:
            event.remove(SearchCycle, "before_insert", _fail_cycle)

        # Service hit its SQLAlchemyError path: generic 500, no 201/200/409.
        assert resp.status_code == 500, resp.get_data(as_text=True)
        # The fault fired after the RideRequest flush (id already assigned).
        assert seen["fired"] is True
        assert seen["ride_request_id"] is not None

        # Fresh-session evidence: neither partial row survived the rollback.
        with app.app_context():
            assert RideRequest.query.filter_by(
                user_id=rider_id, idempotency_key=key,
                is_deleted=False).one_or_none() is None
            assert SearchCycle.query.filter_by(
                cycle_key=expected_cycle_key).one_or_none() is None
            assert Booking.query.count() == bookings_before
        assert _counts(app, rider_id) == (requests_before, cycles_before, 0)
        # Pre-existing rows intact: rider still present.
        with app.app_context():
            from app.identity.models.user import User
            assert db.session.get(User, rider_id) is not None
        # Listener reliably removed even when an assertion above fails.
        assert not event.contains(SearchCycle, "before_insert", _fail_cycle)


    def test_instant_request_ignores_stale_client_pickup_time(self, app, client):
        rider_id = _seed_rider(app, "instantclock")
        _promote_to_tier2(app, rider_id)
        _login_as(app, client, rider_id)
        body = _payload(app, 
            booking_mode="instant",
            pickup_time=(datetime.now(timezone.utc) + timedelta(hours=8)).isoformat(),
        )

        before = datetime.now(timezone.utc)
        resp = client.post(URL, json=body)
        after = datetime.now(timezone.utc)
        assert resp.status_code == 201, resp.get_data(as_text=True)
        parsed = datetime.fromisoformat(resp.get_json()["data"]["pickup_time"])
        assert before - timedelta(seconds=2) <= parsed <= after + timedelta(seconds=2), parsed

    def test_expired_matching_window_closes_without_issuing_an_offer(self, app):
        from app.transport.models import OfferAttempt, RideRequest, SearchCycle
        from app.transport.services.ride_request_service import RideRequestService
        from app.transport.services.ride_request_dispatch_service import (
            RideRequestDispatchService,
        )

        rider_id = _seed_rider(app, "expiredwindow")
        with app.app_context():
            created = RideRequestService.create_request(
                rider_id, _payload(app, booking_mode="instant")
            )
            reference = created["request"].public_id
            cycle = SearchCycle.query.filter_by(
                ride_request_id=created["request"].id, cycle_number=1
            ).one()
            cycle.deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.session.commit()

            outcome = RideRequestDispatchService.start_search(reference)
            db.session.expire_all()
            request_row = RideRequest.query.filter_by(public_id=reference).one()
            cycle = SearchCycle.query.filter_by(
                ride_request_id=request_row.id, cycle_number=1
            ).one()

            assert outcome["status"] == "expired"
            assert request_row.status == "searching"
            assert cycle.status == "expired"
            assert cycle.terminal_reason == "no_supply"
            assert OfferAttempt.query.filter_by(cycle_id=cycle.id).count() == 0

    def test_payment_method_is_required(self, app, client):
        rider_id = _seed_rider(app, "paymentrequired")
        _promote_to_tier2(app, rider_id)
        _login_as(app, client, rider_id)
        body = _payload(app, )
        body.pop("payment_method")

        response = client.post(URL, json=body)
        assert response.status_code == 400, response.get_data(as_text=True)
        assert _counts(app, rider_id) == (0, 0, 0)

    def test_cancelled_search_closes_cycle_without_booking(self, app, client):
        from app.transport.models import Booking, RideRequest, SearchCycle
        from app.transport.services.ride_request_service import RideRequestService
        from app.transport.services.ride_request_dispatch_service import (
            RideRequestDispatchService,
        )

        rider_id = _seed_rider(app, "cancelrequest")
        with app.app_context():
            created = RideRequestService.create_request(rider_id, _payload(app, ))
            reference = created["request"].public_id
            outcome = RideRequestDispatchService.cancel_request(reference, rider_id)
            assert outcome["status"] == "cancelled"

            request_row = RideRequest.query.filter_by(public_id=reference).one()
            cycle = SearchCycle.query.filter_by(
                ride_request_id=request_row.id, cycle_number=1
            ).one()
            assert request_row.status == "cancelled"
            assert request_row.cancelled_at is not None
            assert cycle.status == "cancelled"
            assert cycle.terminal_reason == "rider_cancelled"
            assert Booking.query.filter_by(booking_reference=reference).one_or_none() is None


class TestCommitmentGates:
    def test_anonymous_cannot_create(self, app, client):
        rider_id = _seed_rider(app)
        resp = client.post(URL, json=_payload(app, ))
        assert resp.status_code == 401, resp.get_data(as_text=True)
        assert _counts(app, rider_id) == (0, 0, 0)

    def test_ineligible_rider_redirected_and_creates_nothing(self, app, client):
        from app.auth.kyc_compliance import calculate_kyc_tier

        rider_id = _seed_rider(app)
        with app.app_context():
            assert calculate_kyc_tier(rider_id)["tier"] < 2
        _login_as(app, client, rider_id)
        resp = client.post(URL, json=_payload(app, ), follow_redirects=False)
        assert resp.status_code in (301, 302), resp.get_data(as_text=True)
        assert "kyc" in (resp.headers.get("Location") or "").lower()
        assert _counts(app, rider_id) == (0, 0, 0)


class TestCanonicalValidation:
    @pytest.mark.parametrize("mutate", [
        lambda b: b.pop("dropoff"),
        lambda b: b.update({"pickup": {"address": "typed text only"}}),
        lambda b: b.update({"pickup": {"latitude": "far", "longitude": "away"}}),
        lambda b: b.update({"pickup": {"latitude": 0.31}}),
        lambda b: b.update({"service_type": "teleport"}),
        lambda b: b.pop("idempotency_key"),
    ])
    def test_invalid_payloads_rejected_with_zero_rows(self, app, client, mutate):
        rider_id = _seed_rider(app)
        _promote_to_tier2(app, rider_id)
        _login_as(app, client, rider_id)
        body = _payload(app, )
        mutate(body)
        resp = client.post(URL, json=body)
        assert resp.status_code == 400, resp.get_data(as_text=True)
        assert resp.get_json()["success"] is False
        assert _counts(app, rider_id) == (0, 0, 0)


class TestLegacyPathsUnchanged:
    def test_anonymous_discovery_still_open(self, client):
        # Registered on the transport web blueprint
        # (app/transport/routes.py::api_availability), NOT /api/transport/*.
        resp = client.get("/transport/api/availability")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["success"] is True

    def test_canonical_fare_estimate_still_served(self, client):
        resp = client.post("/api/transport/fare/estimate", json={
            "service_type": "on_demand", "vehicle_class": "comfort",
            "distance_km": 5})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["success"] is True
