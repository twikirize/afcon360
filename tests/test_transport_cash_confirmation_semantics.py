"""
tests/test_transport_cash_confirmation_semantics.py
Focused regression: cash booking produces CONFIRMED with payment_status=PENDING.

Proves the domain separation:
- Booking.status = CONFIRMED (booking accepted, matching active)
- payment_status = PENDING at booking; payment is not captured at booking
- CONFIRMED != payment captured
- CONFIRMED != driver assigned
"""
import pytest
import re
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.transport.models import (
    Booking,
    BookingStatus,
    PaymentStatus,
)
from app.transport.services.matching_service import MatchingService

# Reuse fixtures from the route path test
from tests.test_transport_booking_route_path import (
    _FakeRedis,
    _bolt_form,
    _new_pickup_time,
    _promote_user_to_tier3,
)


def _get_user_id(app, test_user):
    """Safely extract the internal user id from a detached User object."""
    with app.app_context():
        merged = db.session.merge(test_user)
        uid = merged.id
        db.session.rollback()
        return uid


# Use the exact same wording as routes.py (with RIGHT SINGLE QUOTATION MARK U+2019)
NEW_WORDING = "Ride request received! We\u2019re finding your driver. Reference:"
OLD_WORDING = "Booking confirmed! Reference"


class TestCashConfirmationSemantics:
    """Prove cash booking semantics: CONFIRMED with payment_status=PENDING."""

    def test_cash_booking_confirmed_with_pending_payment(
        self, app, authenticated_client, test_user, monkeypatch
    ):
        """
        Cash booking flow:
        1. Creates booking via POST /transport/book
        2. Booking.status = CONFIRMED (matching can start)
        3. payment_status = PENDING (pay-later, not captured)
        4. Matching may begin (discover_and_offer works)
        5. Driver NOT assigned yet
        """
        user_id = _get_user_id(app, test_user)

        # --- Arrange: promote rider to tier-3 (phone + identity verified)
        _promote_user_to_tier3(app, user_id)

        # --- Arrange: FakeRedis for matching service
        fake = _FakeRedis()
        monkeypatch.setattr(
            "app.transport.services.offer_service.redis_client", fake
        )

        # --- Act: POST /transport/book with cash payment
        resp = authenticated_client.post(
            "/transport/book",
            data=_bolt_form(_new_pickup_time()),
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302), f"Expected redirect, got {resp.status_code}"
        location = resp.headers.get("Location", "")
        assert "/transport/rides/" in location, location
        ref = location.rstrip("/").rsplit("/", 1)[1]
        assert ref, "redirect carried no booking reference"

        # --- Assert: Verify booking state in database
        with app.app_context():
            booking = Booking.query.filter_by(booking_reference=ref).first()
            assert booking is not None, "Booking not found in DB"

            # 1. Booking.status = CONFIRMED (claimable, matching active)
            assert booking.status == BookingStatus.CONFIRMED.value, (
                f"Expected CONFIRMED, got {booking.status}"
            )

            # 2. payment_status = PENDING (pay-later, NOT captured)
            assert booking.payment_status == PaymentStatus.PENDING.value, (
                f"Expected PENDING, got {booking.payment_status}"
            )

            # 3. payment_method = cash
            assert booking.payment_method == "cash", (
                f"Expected cash, got {booking.payment_method}"
            )

            # 4. confirmed_at is stamped
            assert booking.confirmed_at is not None, "confirmed_at not stamped"

            # 5. Driver NOT assigned yet
            assert booking.assigned_driver_id is None, (
                f"Driver should not be assigned yet, got {booking.assigned_driver_id}"
            )
            assert booking.assigned_vehicle_id is None, (
                f"Vehicle should not be assigned yet, got {booking.assigned_vehicle_id}"
            )

    def test_confirmed_not_equal_payment_captured(self, app, test_user):
        """
        Explicit proof: CONFIRMED does not imply payment captured.
        """
        user_id = _get_user_id(app, test_user)
        with app.app_context():
            # Create a booking directly with cash
            booking = Booking(
                user_id=user_id,
                provider_type="individual_driver",
                service_type="on_demand",
                pickup_location={"address": "Test Pickup"},
                dropoff_location={"address": "Test Dropoff"},
                pickup_time=datetime.now(timezone.utc) + timedelta(minutes=10),
                passenger_count=1,
                base_price=50.00,
                payment_method="cash",
                payment_status=PaymentStatus.PENDING,
                status=BookingStatus.CONFIRMED,
                confirmed_at=datetime.now(timezone.utc),
            )
            db.session.add(booking)
            db.session.commit()

            # Verify the separation
            assert booking.status == BookingStatus.CONFIRMED.value
            assert booking.payment_status == PaymentStatus.PENDING.value
            assert booking.payment_status != PaymentStatus.CAPTURED.value

    def test_confirmed_not_equal_driver_assigned(self, app, test_user):
        """
        Explicit proof: CONFIRMED does not imply driver assigned.
        """
        user_id = _get_user_id(app, test_user)
        with app.app_context():
            booking = Booking(
                user_id=user_id,
                provider_type="individual_driver",
                service_type="on_demand",
                pickup_location={"address": "Test Pickup"},
                dropoff_location={"address": "Test Dropoff"},
                pickup_time=datetime.now(timezone.utc) + timedelta(minutes=10),
                passenger_count=1,
                base_price=50.00,
                payment_method="cash",
                payment_status=PaymentStatus.PENDING,
                status=BookingStatus.CONFIRMED,
                confirmed_at=datetime.now(timezone.utc),
            )
            db.session.add(booking)
            db.session.commit()

            # Verify driver not assigned
            assert booking.status == BookingStatus.CONFIRMED.value
            assert booking.assigned_driver_id is None
            assert booking.assigned_vehicle_id is None

    def test_matching_can_begin_on_confirmed_cash(self, app, test_user, monkeypatch):
        """
        Matching can begin on CONFIRMED cash booking (payment_status=PENDING).
        
        This proves the matching process is invoked for CONFIRMED bookings
        regardless of payment_status. The outcome may be "no_suitable_drivers"
        if no drivers are seeded, but the matching code path executes.
        """
        user_id = _get_user_id(app, test_user)
        # Arrange: create confirmed cash booking
        with app.app_context():
            booking = Booking(
                user_id=user_id,
                provider_type="individual_driver",
                service_type="on_demand",
                pickup_location={"latitude": 0.3136, "longitude": 32.5811, "address": "Kampala Centre"},
                dropoff_location={"latitude": 0.3161, "longitude": 32.6056, "address": "Nile Independence Stadium"},
                pickup_time=datetime.now(timezone.utc) + timedelta(minutes=10),
                passenger_count=1,
                base_price=50.00,
                payment_method="cash",
                payment_status=PaymentStatus.PENDING,
                status=BookingStatus.CONFIRMED,
                confirmed_at=datetime.now(timezone.utc),
            )
            db.session.add(booking)
            db.session.commit()
            booking_id = booking.id

        # Arrange: FakeRedis
        fake = _FakeRedis()
        monkeypatch.setattr(
            "app.transport.services.offer_service.redis_client", fake
        )

        # Act: discover_and_offer should work (matching starts)
        with app.app_context():
            outcome = MatchingService.discover_and_offer(booking_id)

        # Assert: matching process executes (no exception, returns dict with expected keys)
        assert isinstance(outcome, dict), f"Expected dict, got {type(outcome)}"
        assert "success" in outcome
        assert "reason" in outcome
        assert "offers_created" in outcome
        assert "ranked_count" in outcome
        # The process runs even with payment_status=PENDING - this is the proof
        # Note: offers_created may be 0 if no drivers in pool, but no exception

    def test_rider_success_flash_uses_corrected_wording(
        self, app, authenticated_client, test_user, monkeypatch
    ):
        """
        Rider-facing flash uses corrected wording:
        OLD: "Booking confirmed! Reference: {ref}"
        NEW: "Ride request received! We\u2019re finding your driver. Reference: {ref}"
        """
        user_id = _get_user_id(app, test_user)
        _promote_user_to_tier3(app, user_id)

        fake = _FakeRedis()
        monkeypatch.setattr(
            "app.transport.services.offer_service.redis_client", fake
        )

        resp = authenticated_client.post(
            "/transport/book",
            data=_bolt_form(_new_pickup_time()),
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302)
        location = resp.headers.get("Location", "")
        ref = location.rstrip("/").rsplit("/", 1)[1]

        # Follow redirect to see flash message
        page = authenticated_client.get(location)
        assert page.status_code == 200
        html = page.get_data(as_text=True)

        # Debug: search for flash-related content
        flash_matches = re.findall(r'alert[^>]*>([^<]*)', html)
        if flash_matches:
            print(f"DEBUG: Found flash messages: {flash_matches}")
        
        # NEW wording present with exact reference (uses RIGHT SINGLE QUOTATION MARK U+2019)
        expected_new = f"{NEW_WORDING} {ref}"
        assert expected_new in html, f"New wording not found. Flash messages found: {flash_matches}"

        # OLD wording absent
        assert OLD_WORDING not in html, "Old wording still present"