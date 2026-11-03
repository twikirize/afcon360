"""UI-15 — Flask route tests for /transport/book error and success redirects.

These tests exercise the actual Flask route handler, not mocked browser
intercepts. They verify:
  A. Validation failure -> redirect to transport.home + validation flash
  B. Booking-creation exception -> redirect to transport.home + error flash
  C. Successful mocked booking -> redirect to transport.rides_show + success flash with reference
"""

import pytest
from unittest.mock import patch, MagicMock
from app.utils.exceptions import ValidationError, ServiceUnavailableError
from app.transport.models import BookingStatus


@pytest.fixture(scope="function")
def rider_with_kyc(app):
    """Create a rider user with KYC tier >= 2 (required for booking)."""
    with app.app_context():
        from app.auth.kyc_compliance import calculate_kyc_tier
        from app.extensions import db
        from app.identity.models.roles_permission import get_or_create_role
        from app.identity.models.user import User, UserRole
        from app.identity.individuals.individual_verification import IndividualVerification
        from app.profile.models import UserProfile
        import uuid
        from datetime import date, datetime, timezone

        user = User(
            public_id=str(uuid.uuid4()),
            username=f"rider_{uuid.uuid4().hex[:8]}",
            email=f"rider_{uuid.uuid4().hex[:8]}@test.example.com",
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

        profile = UserProfile(
            user_id=user.public_id,
            full_name="Test Rider",
            date_of_birth=date(1995, 4, 12),
            nationality="UG",
            id_type="national_id",
            id_number=f"NID-TEST-{uuid.uuid4().hex[:8].upper()}",
            profile_completed=True,
            verification_status="verified",
        )
        db.session.add(profile)
        db.session.flush()

        db.session.add(
            IndividualVerification(
                user_id=user.id, status="verified", scope={"national_id": True, "biometric": True}
            )
        )
        db.session.commit()

        tier = calculate_kyc_tier(user.id)["tier"]
        assert tier >= 2, f"Expected KYC tier >= 2, got {tier}"

        # Return the user's public_id for login
        return str(user.public_id)


class TestUI15BookRedirects:
    """UI-15 /transport/book redirect behavior under real Flask handler."""

    def test_validation_failure_redirects_to_home_with_flash(
        self, client, rider_with_kyc, app
    ):
        """Submit a payload missing required fields; assert canonical redirect and flash."""
        # Login the rider using Flask-Login session
        with client.session_transaction() as sess:
            sess['_user_id'] = rider_with_kyc
            sess['_fresh'] = True

        # Missing required fields: pickup_location, dropoff_location, pickup_time, service_type
        payload = {
            "vehicle_class": "comfort",
            "payment_method": "cash",
        }
        resp = client.post(
            "/transport/book",
            data=payload,
            follow_redirects=False,
        )
        # Should redirect to transport.home (the rider entry endpoint = /transport/)
        assert resp.status_code == 302
        assert "/transport/" == resp.headers["Location"] or "/transport/" in resp.headers["Location"]
        # Follow redirect and check flash
        resp_follow = client.get(resp.headers["Location"])
        assert resp_follow.status_code == 200
        html = resp_follow.get_data(as_text=True)
        # Validation flash should be present (pickup_location is required)
        assert "Pickup Location is required" in html or "pickup_location" in html.lower()

    def test_booking_creation_exception_redirects_to_home_with_flash(
        self, client, rider_with_kyc, app
    ):
        """Mock booking service to raise; assert canonical redirect and flash."""
        # Login the rider
        with client.session_transaction() as sess:
            sess['_user_id'] = rider_with_kyc
            sess['_fresh'] = True

        with app.app_context():
            from app.transport.services import booking_service as bs_module

            def raise_exception(*args, **kwargs):
                raise RuntimeError("Simulated booking creation failure")

            with patch.object(
                bs_module.BookingService, "create_booking", raise_exception
            ):
                # Submit a valid-looking payload (will pass initial validation)
                payload = {
                    "pickup_location": '{"latitude": 0.34, "longitude": 32.58}',
                    "dropoff_location": '{"latitude": 0.35, "longitude": 32.59}',
                    "pickup_latitude": "0.34",
                    "pickup_longitude": "32.58",
                    "dropoff_latitude": "0.35",
                    "dropoff_longitude": "32.59",
                    "pickup_time": "2099-12-31T10:00:00",
                    "service_type": "on_demand",
                    "vehicle_class": "comfort",
                    "payment_method": "cash",
                    "passenger_count": "1",
                    "idempotency_key": f"test-key-{rider_with_kyc[:8]}",
                }
                resp = client.post(
                    "/transport/book",
                    data=payload,
                    follow_redirects=False,
                )
                assert resp.status_code == 302
                assert "/transport/" == resp.headers["Location"] or "/transport/" in resp.headers["Location"]
                # Follow redirect and check flash
                resp_follow = client.get(resp.headers["Location"])
                assert resp_follow.status_code == 200
                html = resp_follow.get_data(as_text=True)
                assert "Booking error" in html or "danger" in html.lower()

    def test_successful_mocked_booking_redirects_to_rides_show_with_reference(
        self, client, rider_with_kyc, app
    ):
        """A valid quote creates a durable request and redirects by public reference."""
        with client.session_transaction() as sess:
            sess["_user_id"] = rider_with_kyc
            sess["_fresh"] = True

        from tests.transport.test_ride_request_create import _payload as signed_quote_payload
        quote = signed_quote_payload(app, idempotency_key=f"ui15-{rider_with_kyc[:8]}")
        with app.app_context():
            from app.extensions import db
            from app.transport.models import Booking, RideRequest
            from app.transport.services.ride_request_dispatch_service import RideRequestDispatchService

            with patch.object(
                RideRequestDispatchService, "start_search",
                return_value={"status": "started"},
            ):
                payload = {
                    "pickup_location": quote["pickup"]["address"],
                    "dropoff_location": quote["dropoff"]["address"],
                    "pickup_latitude": str(quote["pickup"]["latitude"]),
                    "pickup_longitude": str(quote["pickup"]["longitude"]),
                    "dropoff_latitude": str(quote["dropoff"]["latitude"]),
                    "dropoff_longitude": str(quote["dropoff"]["longitude"]),
                    "pickup_time": quote["pickup_time"],
                    "service_type": "on_demand",
                    "booking_mode": "instant",
                    "vehicle_class": quote["vehicle_class"],
                    "payment_method": quote["payment_method"],
                    "passenger_count": str(quote["passenger_count"]),
                    "currency": quote["currency"],
                    "confirmed_fare_amount": quote["confirmed_fare_amount"],
                    "fare_quote_token": quote["fare_quote_token"],
                    "idempotency_key": quote["idempotency_key"],
                }
                resp = client.post("/transport/book", data=payload, follow_redirects=False)

            assert resp.status_code == 302
            assert resp.headers["Location"].startswith("/transport/rides/")
            reference = resp.headers["Location"].rsplit("/", 1)[-1]
            assert reference
            assert RideRequest.query.filter_by(public_id=reference).first() is not None
            assert Booking.query.filter_by(
                idempotency_key=quote["idempotency_key"], is_deleted=False
            ).first() is None
            with client.session_transaction() as sess:
                flashes = sess.get("_flashes", [])
                assert any("Fare confirmed" in msg[1] and reference in msg[1]
                           for msg in flashes)
            db.session.rollback()
