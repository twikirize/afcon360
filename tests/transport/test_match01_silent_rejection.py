"""MATCH-01: silent driver rejection.

Driver declines an offer -> the booking stays CONFIRMED, the rider surface
does not change, the decline is recorded in the durable offer ledger
(admin-visible only), and the decline is NOT a cancellation (booking
cancellation_* fields untouched, driver cancellation_rate untouched).
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from tests.test_transport_concurrent_claim import _FakeRedis

pytestmark = pytest.mark.usefixtures("db_session")


def _seed_rider(app):
    from app.identity.models.user import User

    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"m1r_{uid}",
                    email=f"m1r_{uid}@test.example.com",
                    is_active=True, is_verified=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.commit()
        return user.id


def _seed_confirmed_booking(app, rider_id):
    from app.transport.models import (
        Booking, BookingStatus, ProviderType, ServiceType,
    )

    with app.app_context():
        now = datetime.now(timezone.utc)
        booking = Booking(
            booking_reference=f"M1-{uuid.uuid4().hex[:8].upper()}",
            user_id=rider_id,
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=ServiceType.ON_DEMAND,
            pickup_location={"latitude": 0.3136, "longitude": 32.5811},
            dropoff_location={"latitude": 0.3476, "longitude": 32.5825},
            pickup_time=now + timedelta(hours=1),
            passenger_count=1, base_price=Decimal("10.00"),
            subtotal=Decimal("10.00"), total_amount=Decimal("10.00"),
            final_price=Decimal("10.00"), status=BookingStatus.CONFIRMED,
            confirmed_at=now,
            booking_metadata={"matching_started_at": now.isoformat()},
        )
        db.session.add(booking)
        db.session.commit()
        return booking.id, booking.booking_reference


def _patch_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(
        "app.transport.services.offer_service.redis_client", fake)
    return fake


class TestSilentRejection:
    def test_decline_keeps_booking_confirmed(self, app, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from app.transport.services.offer_service import OfferService

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context():
            OfferService.create_offer(ref, 101, 201)
            assert OfferService.decline_offer(ref, 101) is True
            stored = db.session.get(Booking, booking_id)
            assert stored.status == BookingStatus.CONFIRMED
            assert stored.status == "confirmed"
            assert type(stored.status) is str
            # Not a cancellation: cancellation fields untouched.
            assert stored.cancellation_reason is None
            assert stored.cancelled_at is None
            assert stored.no_match_reason is None

    def test_decline_recorded_in_durable_ledger(self, app, monkeypatch):
        from app.transport.models import Booking
        from app.transport.services.offer_service import OfferService

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context():
            OfferService.create_offer(ref, 101, 201)
            OfferService.decline_offer(ref, 101)
            stored = db.session.get(Booking, booking_id)
            attempts = (stored.booking_metadata or {}).get("offer_attempts", [])
            declined = [a for a in attempts if a.get("outcome") == "declined"]
            assert len(declined) == 1
            assert declined[0]["driver_id"] == 101

    def test_decline_does_not_touch_driver_cancellation_rate(
            self, app, monkeypatch):
        from app.transport.models import DriverProfile
        from app.transport.services.offer_service import OfferService
        from tests.transport.test_driver_console import _make_ready, _seed_driver

        driver = _seed_driver(app)
        _make_ready(app, driver)
        rider_id = _seed_rider(app)
        _, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context():
            profile = db.session.get(DriverProfile, driver.driver_profile_id)
            before_cancel = profile.cancellation_rate
            before_accept = profile.acceptance_rate
            OfferService.create_offer(ref, profile.id, 301)
            assert OfferService.decline_offer(ref, profile.id) is True
            db.session.refresh(profile)
            assert profile.cancellation_rate == before_cancel
            assert profile.acceptance_rate == before_accept

    def test_rider_json_has_no_reject_mention_during_matching(
            self, app, client, monkeypatch):
        from app.transport.services.offer_service import OfferService
        from tests.test_geo_rider_tracking import _rider_client

        rider_id = _seed_rider(app)
        _, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context():
            OfferService.create_offer(ref, 101, 201)
            OfferService.decline_offer(ref, 101)
        _rider_client(app, client, rider_id)
        resp = client.get(f"/api/transport/bookings/{ref}")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        blob = resp.get_data(as_text=True).lower()
        assert "reject" not in blob
        assert "declin" not in blob
        assert "refus" not in blob
