"""Regression tests for the 2026-10-24 booking_mode fix (E1-E10),
extended by PICKUP-TIME-AUTHORITY-P1 (server clock authority).

Proves end-to-end:
- instant booking with pickup_time=now commits (the 13:53 failure is fixed)
- instant booking with up to 5min latency commits (ck_pickup_time_sane grace)
- instant booking with a STALE client pickup_time commits with a
  SERVER-stamped time (client value ignored — P1 flips the old
  beyond-grace rejection)
- scheduled +30min commits
- scheduled +3min is rejected by app validation (before DB)
- scheduled with naive pickup_time interprets as Africa/Nairobi

Every test uses a probe user created in the test DB. Cleanup is per-test.
"""
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.extensions import db
from app.identity.models.user import User
from app.transport.models import Booking
from app.transport.services.booking_service import get_booking_service
from app.utils.exceptions import ServiceUnavailableError, ValidationError


NAIROBI = ZoneInfo("Africa/Nairobi")


@pytest.fixture
def probe_user(app):
    """Minimal user for the booking FK. Best-effort cleanup on teardown."""
    email = f"probe_{uuid.uuid4().hex[:12]}@afcon360.local"
    user = User(email=email, is_active=True, is_verified=True)
    if hasattr(User, "public_id") and not getattr(user, "public_id", None):
        # Column is varchar; the model's own default yields str (user.py:78).
        # A raw UUID object makes psycopg2 bind pg-uuid → varchar = uuid fails.
        user.public_id = str(uuid.uuid4())
    # password_hash is NOT NULL with no default (user.py); use the model's
    # own setter rather than writing the hash column directly.
    user.set_password(f"Probe!{uuid.uuid4().hex[:12]}")
    db.session.add(user)
    db.session.commit()
    yield user
    try:
        Booking.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _payload(mode: str, pickup_time: datetime) -> dict:
    """Mirror of the frontend form fields for create_booking."""
    return {
        "service_type": "on_demand",
        "provider_type": "individual_driver",
        "pickup_latitude": 0.3136,
        "pickup_longitude": 32.5811,
        "dropoff_latitude": 0.3476,
        "dropoff_longitude": 32.5825,
        "pickup_location": "Kampala",
        "dropoff_location": "Entebbe",
        "pickup_time": pickup_time.isoformat(),
        "passenger_count": 1,
        "currency": "USD",
        "payment_method": "cash",
        "vehicle_class": "comfort",
        "booking_mode": mode,
    }


class TestBookingModeFix:
    def test_instant_now_commits(self, probe_user):
        """The 13:53 case: instant booking, pickup_time = now."""
        result = get_booking_service().create_booking(
            probe_user.id, _payload("instant", datetime.now(timezone.utc))
        )
        assert result["success"] is True
        booking = Booking.query.filter_by(
            booking_reference=result["data"]["booking_reference"]
        ).first()
        assert booking is not None
        assert booking.booking_metadata["booking_mode"] == "instant"

    def test_instant_with_latency_commits(self, probe_user):
        """Simulate 2-minute latency: pickup_time 2min in the past.

        chk_pickup_time_sane (5-min grace) should allow it.
        This is the exact failure mode chk_pickup_time_future had.
        """
        now = datetime.now(timezone.utc)
        result = get_booking_service().create_booking(
            probe_user.id, _payload("instant", now - timedelta(minutes=2))
        )
        assert result["success"] is True

    def test_instant_beyond_grace_now_server_stamped(self, probe_user):
        """PICKUP-TIME-AUTHORITY-P1 flips the old beyond-grace behavior.

        A stale client pickup_time on an instant ride is IGNORED — the
        server clock is the authority. The old behavior (client time
        honoured, ck_pickup_time_sane rejects as ServiceUnavailableError)
        is closed; the booking now commits with a server-now pickup_time
        inside the 5-minute grace window.
        """
        stale = datetime.now(timezone.utc) - timedelta(minutes=10)
        result = get_booking_service().create_booking(
            probe_user.id, _payload("instant", stale)
        )
        assert result["success"] is True
        booking = Booking.query.filter_by(
            booking_reference=result["data"]["booking_reference"]
        ).first()
        assert booking is not None
        # Server-stamped: within the ck_pickup_time_sane grace of now,
        # nowhere near the stale client value.
        drift = abs(
            (booking.pickup_time - datetime.now(timezone.utc)).total_seconds())
        assert drift < 300
        # The return dict carries the server value, not the client's.
        assert result["data"]["pickup_time"] == booking.pickup_time.isoformat()

    def test_scheduled_future_commits(self, probe_user):
        """Scheduled +30min should pass E6b validation and commit."""
        now = datetime.now(timezone.utc)
        result = get_booking_service().create_booking(
            probe_user.id, _payload("scheduled", now + timedelta(minutes=30))
        )
        assert result["success"] is True
        booking = Booking.query.filter_by(
            booking_reference=result["data"]["booking_reference"]
        ).first()
        assert booking.booking_metadata["booking_mode"] == "scheduled"

    def test_scheduled_near_past_rejected_by_app(self, probe_user):
        """E6b: scheduled +3min fails in Python before reaching the DB."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            get_booking_service().create_booking(
                probe_user.id, _payload("scheduled", now + timedelta(minutes=3))
            )
        message = str(exc_info.value.message)
        assert "at least 15 minutes" in message
        assert "Now" in message  # the guidance suffix

    def test_naive_timestamp_interpreted_as_nairobi(self, probe_user):
        """E6c: naive pickup_time is Africa/Nairobi, not UTC or machine-local.

        Construct "20min from now" as Nairobi wall time (no tzinfo).
        If E6c works, it parses to 20min-future UTC → passes.
        If E6c regressed to UTC or machine-local, this becomes
        hours-in-the-past → rejected.
        """
        now = datetime.now(timezone.utc)
        naive_nairobi = (
            (now + timedelta(minutes=20)).astimezone(NAIROBI).replace(tzinfo=None)
        )
        result = get_booking_service().create_booking(
            probe_user.id, _payload("scheduled", naive_nairobi)
        )
        assert result["success"] is True
