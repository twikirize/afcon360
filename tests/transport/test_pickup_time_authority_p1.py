"""PICKUP-TIME-AUTHORITY-P1 — Deploy 1 behavior contract.

Covers the Deploy-1 (code-only, no schema change) half of the node:
- booking_mode is hard-required: missing / blank / invalid rejected
- scheduled cash rides stay PENDING_PAYMENT at the route (no immediate
  confirm/dispatch; the Deploy-2 30-minute scheduler owns release)
- instant cash rides still confirm + dispatch at the route (control)
- retry_matching: confirmed_at is immutable, status + cursor + audit
  commit in ONE transaction, exactly one concurrent retry wins
- Booking.is_upcoming: NULL-safe and scheduled-aware
- _split_rides: a live scheduled ride stays upcoming while its
  server-authoritative pickup_time is still NULL
- the scheduled 15-minute lead boundary is measured from request
  receipt (6C), not from a post-processing clock read
"""
import uuid
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from app.extensions import db
from app.identity.models.user import User
from app.transport.models import Booking, BookingStatus, ProviderType, ServiceType
from app.transport.services.booking_service import (
    BookingService,
    get_booking_service,
)
from app.utils.exceptions import ValidationError


def _payload(**over):
    """Valid instant payload mirroring the rider form contract."""
    data = {
        "service_type": "on_demand",
        "provider_type": "individual_driver",
        "booking_mode": "instant",
        "pickup_latitude": 0.3136,
        "pickup_longitude": 32.5811,
        "dropoff_latitude": 0.3476,
        "dropoff_longitude": 32.5825,
        "pickup_location": "Kampala",
        "dropoff_location": "Entebbe",
        "pickup_time": (datetime.now(timezone.utc) + timedelta(hours=1)
                        ).isoformat(),
        "passenger_count": 1,
        "currency": "USD",
        "payment_method": "cash",
        "vehicle_class": "comfort",
    }
    data.update(over)
    return data


@pytest.fixture
def probe_user(app):
    """Minimal user for the booking FK. Best-effort cleanup on teardown."""
    email = f"p1_{uuid.uuid4().hex[:12]}@afcon360.local"
    user = User(email=email, is_active=True, is_verified=True)
    if hasattr(User, "public_id") and not getattr(user, "public_id", None):
        user.public_id = str(uuid.uuid4())
    user.set_password(f"P1!{uuid.uuid4().hex[:12]}")
    db.session.add(user)
    db.session.commit()
    yield user
    try:
        Booking.query.filter_by(user_id=user.id).delete(
            synchronize_session=False)
        db.session.delete(user)
        db.session.commit()
    except Exception:
        db.session.rollback()


# ---------------------------------------------------------------------------
# booking_mode is hard-required (patch #1)
# ---------------------------------------------------------------------------

class TestBookingModeRequired:

    def test_missing_booking_mode_rejected(self, probe_user):
        data = _payload()
        del data["booking_mode"]
        with pytest.raises(ValidationError) as exc:
            get_booking_service().create_booking(probe_user.id, data)
        assert exc.value.field == "booking_mode"
        assert Booking.query.filter_by(user_id=probe_user.id).count() == 0

    def test_blank_booking_mode_rejected(self, probe_user):
        with pytest.raises(ValidationError) as exc:
            get_booking_service().create_booking(
                probe_user.id, _payload(booking_mode="   "))
        assert exc.value.field == "booking_mode"

    def test_invalid_booking_mode_rejected(self, probe_user):
        with pytest.raises(ValidationError) as exc:
            get_booking_service().create_booking(
                probe_user.id, _payload(booking_mode="later"))
        assert exc.value.field == "booking_mode"

    def test_return_dict_carries_server_booking_mode(self, probe_user):
        result = get_booking_service().create_booking(
            probe_user.id, _payload(booking_mode="scheduled",
                                    pickup_time=(datetime.now(timezone.utc)
                                                 + timedelta(minutes=45)
                                                 ).isoformat()))
        assert result["success"] is True
        assert result["data"]["booking_mode"] == "scheduled"


# ---------------------------------------------------------------------------
# Route cash gate: scheduled stays PENDING_PAYMENT, instant confirms (patch #5)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def rider_with_kyc(app):
    """Rider with KYC tier >= 2 and a completed profile (booking gates)."""
    from datetime import date
    from app.auth.kyc_compliance import calculate_kyc_tier
    from app.identity.individuals.individual_verification import (
        IndividualVerification,
    )
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import UserRole
    from app.profile.models import UserProfile

    # Tests that request ``client`` get no outer context from
    # _push_request_context, so this fixture owns its app context.
    with app.app_context():
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"p1r_{uuid.uuid4().hex[:8]}",
            email=f"p1r_{uuid.uuid4().hex[:8]}@test.example.com",
            phone=f"+2567{uuid.uuid4().hex[:7]}",
        )
        user.set_password("TestPass123!")
        user.is_active = True
        user.is_verified = True
        user.email_verified = True
        user.phone_verified = True
        user.phone_verified_at = datetime.now(timezone.utc)
        db.session.add(user)
        db.session.flush()

        role = get_or_create_role("user", level=6)
        db.session.add(UserRole(user_id=user.id, role_id=role.id))

        db.session.add(UserProfile(
            user_id=user.public_id,
            full_name="P1 Rider",
            date_of_birth=date(1995, 4, 12),
            nationality="UG",
            id_type="national_id",
            id_number=f"NID-P1-{uuid.uuid4().hex[:8].upper()}",
            profile_completed=True,
            verification_status="verified",
        ))
        db.session.flush()
        db.session.add(IndividualVerification(
            user_id=user.id, status="verified",
            scope={"national_id": True, "biometric": True},
        ))
        db.session.commit()

        assert calculate_kyc_tier(user.id)["tier"] >= 2
        uid = user.id
        public_id = str(user.public_id)

    yield public_id
    with app.app_context():
        try:
            Booking.query.filter_by(user_id=uid).delete(
                synchronize_session=False)
            UserRole.query.filter_by(user_id=uid).delete(
                synchronize_session=False)
            User.query.filter_by(id=uid).delete(synchronize_session=False)
            db.session.commit()
        except Exception:
            db.session.rollback()


def _login(client, public_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = public_id
        sess["_fresh"] = True


def _form(**over):
    data = {
        "service_type": "on_demand",
        "provider_type": "individual_driver",
        "booking_mode": "instant",
        "pickup_latitude": "0.3136",
        "pickup_longitude": "32.5811",
        "dropoff_latitude": "0.3476",
        "dropoff_longitude": "32.5825",
        "pickup_location": "Kampala",
        "dropoff_location": "Entebbe",
        "pickup_time": (datetime.now(timezone.utc) + timedelta(hours=1)
                        ).isoformat(),
        "passenger_count": "1",
        "currency": "USD",
        "payment_method": "cash",
        "vehicle_class": "comfort",
        "idempotency_key": f"p1-{uuid.uuid4().hex}",
    }
    data.update(over)
    return data


class TestRouteCashGate:

    def test_scheduled_cash_ride_stays_pending_payment(
            self, client, rider_with_kyc):
        """P1: the route must NOT confirm/dispatch a scheduled cash ride;
        it stays PENDING_PAYMENT until the Deploy-2 30-min scheduler."""
        _login(client, rider_with_kyc)
        form = _form(
            booking_mode="scheduled",
            pickup_time=(datetime.now(timezone.utc)
                         + timedelta(minutes=45)).isoformat())
        resp = client.post("/transport/book", data=form,
                           follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers["Location"]
        assert "/transport/rides/" in location
        ref = location.rsplit("/", 1)[-1]
        with client.application.app_context():
            booking = Booking.query.filter_by(booking_reference=ref).first()
        assert booking is not None
        assert booking.status == BookingStatus.PENDING_PAYMENT.value

    def test_instant_cash_ride_confirms_at_route(
            self, client, rider_with_kyc):
        """Control: the immediate confirm/dispatch for cash INSTANT rides
        is unchanged."""
        _login(client, rider_with_kyc)
        resp = client.post("/transport/book", data=_form(),
                           follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers["Location"]
        assert "/transport/rides/" in location
        ref = location.rsplit("/", 1)[-1]
        with client.application.app_context():
            booking = Booking.query.filter_by(booking_reference=ref).first()
        assert booking is not None
        assert booking.status == BookingStatus.CONFIRMED.value


# ---------------------------------------------------------------------------
# retry_matching atomicity + confirmed_at immutability (patch #6)
# ---------------------------------------------------------------------------

def _seed_no_match_booking(user_id):
    now = datetime.now(timezone.utc)
    booking = Booking(
        booking_reference=f"P1R-{uuid.uuid4().hex[:10].upper()}",
        user_id=user_id,
        provider_type=ProviderType.INDIVIDUAL_DRIVER,
        service_type=ServiceType.ON_DEMAND,
        pickup_location={"latitude": 0.3476, "longitude": 32.5825},
        dropoff_location={"latitude": 0.3130, "longitude": 32.5812},
        pickup_time=now + timedelta(hours=2),
        passenger_count=1,
        base_price=10.00, subtotal=10.00, total_amount=10.00,
        final_price=10.00,
        status=BookingStatus.NO_MATCH,
        no_match_reason="no_supply",
        confirmed_at=now - timedelta(minutes=10),
    )
    db.session.add(booking)
    db.session.commit()
    return booking.id


class TestRetryAtomicity:

    def test_retry_preserves_confirmed_at_and_refreshes_cursor(
            self, probe_user):
        booking_id = _seed_no_match_booking(probe_user.id)
        before = db.session.get(Booking, booking_id)
        old_confirmed = before.confirmed_at
        assert old_confirmed is not None

        out = BookingService.retry_matching(booking_id, probe_user.id)
        assert out["replayed"] is False
        after = out["booking"]
        # confirmed_at is first-confirmation audit history: byte-identical.
        assert after.confirmed_at == old_confirmed
        assert after.status == BookingStatus.CONFIRMED
        assert after.no_match_reason is None
        meta = after.booking_metadata or {}
        cursor = meta.get("matching_started_at")
        assert cursor is not None
        cursor_dt = datetime.fromisoformat(cursor)
        assert abs((datetime.now(timezone.utc) - cursor_dt).total_seconds()) < 120
        actions = [e.get("action") for e in (after.audit_log or [])]
        assert "retry_matching" in actions

    def test_retry_rejected_from_other_statuses(self, probe_user):
        booking_id = _seed_no_match_booking(probe_user.id)
        booking = db.session.get(Booking, booking_id)
        booking.status = BookingStatus.CONFIRMED
        booking.no_match_reason = None
        db.session.commit()
        with pytest.raises(ValidationError):
            BookingService.retry_matching(booking_id, probe_user.id)

    @pytest.mark.threaded
    def test_concurrent_retry_only_one_wins(self, probe_user, app):
        """Two racing rider retries: the FOR UPDATE lock serializes them;
        exactly one transitions NO_MATCH -> CONFIRMED, the loser is a
        clean client error."""
        booking_id = _seed_no_match_booking(probe_user.id)
        user_id = probe_user.id

        def attempt():
            # Flask contexts are thread-local: each worker owns one and
            # returns plain values (the ORM row must not escape).
            with app.app_context():
                try:
                    out = BookingService.retry_matching(booking_id, user_id)
                    return ("ok", out["replayed"])
                except ValidationError as e:
                    return ("validation", str(e))

        try:
            outcomes = []
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(attempt) for _ in range(2)]
                for f in as_completed(futures):
                    outcomes.append(f.result())
            with app.app_context():
                final_status = db.session.get(Booking, booking_id).status
        finally:
            Booking.query.filter_by(id=booking_id).delete(
                synchronize_session=False)
            db.session.commit()

        wins = [o for o in outcomes if o[0] == "ok"]
        losses = [o for o in outcomes if o[0] == "validation"]
        assert len(wins) == 1, outcomes
        assert len(losses) == 1, outcomes
        # The winner performed the transition, not a replay.
        assert wins[0][1] is False
        assert final_status == BookingStatus.CONFIRMED


# ---------------------------------------------------------------------------
# is_upcoming: NULL-safe + scheduled-aware (patch #9)
# ---------------------------------------------------------------------------

class TestIsUpcoming:

    def _booking(self, **over):
        b = Booking(
            status=BookingStatus.CONFIRMED,
            pickup_time=datetime.now(timezone.utc) + timedelta(hours=1),
            booking_metadata={},
        )
        for k, v in over.items():
            setattr(b, k, v)
        return b

    def test_live_instant_with_future_pickup_is_upcoming(self):
        assert self._booking().is_upcoming is True

    def test_live_instant_with_null_pickup_is_not_upcoming(self):
        b = self._booking(pickup_time=None)
        assert b.is_upcoming is False

    def test_live_scheduled_with_null_pickup_is_upcoming(self):
        """Deploy-2 contract made defensive now: a scheduled ride whose
        server pickup_time is not yet released is still upcoming."""
        b = self._booking(
            pickup_time=None,
            booking_metadata={"booking_mode": "scheduled"},
        )
        assert b.is_upcoming is True

    def test_stale_instant_pickup_is_not_upcoming(self):
        b = self._booking(pickup_time=datetime.now(timezone.utc)
                          - timedelta(minutes=5))
        assert b.is_upcoming is False

    def test_completed_is_not_upcoming(self):
        b = self._booking(status=BookingStatus.COMPLETED)
        assert b.is_upcoming is False


# ---------------------------------------------------------------------------
# _split_rides mode awareness (patch #11)
# ---------------------------------------------------------------------------

class TestSplitRides:

    def test_live_scheduled_with_null_pickup_stays_upcoming(self):
        from app.transport.routes import _split_rides
        now_iso = datetime.now(timezone.utc).isoformat()
        upcoming, past = _split_rides([{
            "status": "confirmed",
            "pickup_time": None,
            "booking_mode": "scheduled",
            "created_at": now_iso,
        }])
        assert len(upcoming) == 1 and not past

    def test_live_instant_with_null_pickup_is_past(self):
        from app.transport.routes import _split_rides
        now_iso = datetime.now(timezone.utc).isoformat()
        upcoming, past = _split_rides([{
            "status": "confirmed",
            "pickup_time": None,
            "booking_mode": "instant",
            "created_at": now_iso,
        }])
        assert not upcoming and len(past) == 1

    def test_legacy_rows_without_mode_keep_old_behavior(self):
        from app.transport.routes import _split_rides
        now_iso = datetime.now(timezone.utc).isoformat()
        upcoming, past = _split_rides([
            {"status": "confirmed",
             "pickup_time": (datetime.now(timezone.utc) + timedelta(hours=1)
                             ).isoformat(),
             "created_at": now_iso},
            {"status": "completed",
             "pickup_time": (datetime.now(timezone.utc) + timedelta(hours=1)
                             ).isoformat(),
             "created_at": now_iso},
        ])
        assert len(upcoming) == 1 and len(past) == 1


# ---------------------------------------------------------------------------
# Scheduled lead boundary from request receipt (6C)
# ---------------------------------------------------------------------------

class TestScheduledLeadFromReceipt:

    def test_lead_boundary_uses_request_receipt(self, probe_user,
                                                monkeypatch):
        """The 15-minute scheduled lead is measured from request receipt.

        Frozen clock: pickup exactly receipt+15min commits; one second
        earlier is a field-precise client error.
        """
        import app.transport.services.booking_service as bs_module

        frozen = datetime.now(timezone.utc).replace(microsecond=0)

        class _FrozenDT(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return frozen
                return frozen.astimezone(tz)

        monkeypatch.setattr(bs_module, "datetime", _FrozenDT)

        ok = get_booking_service().create_booking(
            probe_user.id,
            _payload(booking_mode="scheduled",
                     pickup_time=(frozen + timedelta(minutes=15)).isoformat()))
        assert ok["success"] is True

        with pytest.raises(ValidationError) as exc:
            get_booking_service().create_booking(
                probe_user.id,
                _payload(
                    booking_mode="scheduled",
                    pickup_time=(frozen + timedelta(minutes=15, seconds=-1)
                                 ).isoformat()))
        assert "at least 15 minutes" in str(exc.value.message)
