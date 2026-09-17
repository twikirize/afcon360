import uuid
import pytest
from datetime import date, timedelta
from app.extensions import db
from app.accommodation.models.property import Property, AccommodationPropertyType, AccommodationCancellationPolicy
from app.accommodation.models.room import RoomType, InventoryBlock
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus, AccommodationPaymentStatus
from app.accommodation.services.host_service import HostService
from app.accommodation.services.booking_service import BookingService
from app.identity.models.user import User
from app.identity.models.organization_types import OrganizationType

@pytest.fixture(autouse=True)
def setup_postgres(app):
    with app.app_context():
        # Tests run against the existing Postgres schema
        # We rely on nested transactions or manual cleanup if needed
        # But for now, we just let SQLAlchemy handle the session and rollback
        db.session.begin_nested()
        yield
        db.session.rollback()
        db.session.remove()

def test_property_creation_does_not_create_inventory(app):
    with app.app_context():
        # Setup test users
        host = User.query.filter_by(email="host_test@example.com").first()
        if not host:
            host = User(username="host_test", email="host_test@example.com", is_verified=True, is_active=True)
            host.set_password("Password123!")
            db.session.add(host)
            db.session.commit()

        # Create Property
        property_data = {
            "title": "Marriott Nakasero Test",
            "summary": "Beautiful luxury hotel in Kampala",
            "description": "Premium luxury accommodations",
            "property_type": "hotel",
            "listing_type": "private_room",
            "address_line1": "Nakasero Hill Road",
            "city": "Kampala",
            "country": "UG",
            "max_guests": 4,
            "bedrooms": 2,
            "beds": 3,
            "bathrooms": 2.0,
            "base_price_per_night": 150.00,
            "currency": "USD",
            "cleaning_fee": 30.00,
            "service_fee_pct": 10.00,
            "cancellation_policy": "moderate",
            "min_stay_nights": 1,
            "instant_book": True,
        }

        # Stage 4B-6 / G-1: an organisation-owned Property may only be created
        # through HostService.create_property when the organisation is
        # accommodation-eligible (can_org_host) AND its accommodation provider
        # capability is ACTIVATED. Use a genuine eligible+activated org instead
        # of a fabricated id (a fake owner_org_id is now correctly rejected).
        from app.identity.models.organisation import Organisation
        from app.identity.models.organisation_provider_capability import (
            ProviderCapabilityCode, ProviderCapabilityStatus,
        )
        from app.identity.models.provider_participation import ProviderParticipation

        org = Organisation(
            org_id=f"org_{uuid.uuid4().hex[:10]}",
            legal_name=f"RoomType Org {uuid.uuid4().hex[:8]}",
            country="UG",
            business_category=OrganizationType.HOTEL,
            verification_status="verified",
            lifecycle_state="registered",
            is_active=True,
            is_operational=True,
        )
        db.session.add(org)
        db.session.flush()
        db.session.add(
            ProviderParticipation(
                user_id=None,
                organisation_id=org.id,
                capability_code=ProviderCapabilityCode.ACCOMMODATION.value,
                status=ProviderCapabilityStatus.ACTIVATED.value,
            )
        )
        db.session.flush()

        # Create property - approved lifecycle: creation must NOT auto-create
        # any RoomType/inventory. Inventory is configured separately afterward.
        prop = HostService.create_property(property_data, owner_user_id=None, owner_org_id=org.id)
        db.session.commit()

        assert prop.id is not None

        # Verify NO RoomType was auto-created
        rts = RoomType.query.filter_by(property_id=prop.id).all()
        assert rts == []

        # Update Property must not manufacture inventory either
        update_data = property_data.copy()
        update_data["title"] = "Marriott Nakasero Updated"
        update_data["max_guests"] = 5
        update_data["base_price_per_night"] = 180.00

        HostService.update_property(prop, update_data)
        db.session.commit()

        # Verify still no RoomType after update
        rts_after = RoomType.query.filter_by(property_id=prop.id).all()
        assert rts_after == []

def test_available_units_and_booking_creation(app):
    with app.app_context():
        # Setup test users
        host = User.query.filter_by(email="host_test@example.com").first()
        if not host:
            host = User(username="host_test", email="host_test@example.com", is_verified=True, is_active=True)
            host.set_password("Password123!")
            db.session.add(host)
            db.session.commit()

        guest = User.query.filter_by(email="guest_test@example.com").first()
        if not guest:
            guest = User(username="guest_test", email="guest_test@example.com", is_verified=True, is_active=True)
            guest.set_password("Password123!")
            db.session.add(guest)
            db.session.commit()

        # Create Property
        property_data = {
            "title": "Kampala Suites Test",
            "summary": "Luxury suites",
            "description": "Premium accommodations",
            "property_type": "hotel",
            "listing_type": "private_room",
            "address_line1": "Naguru Hill",
            "city": "Kampala",
            "country": "UG",
            "max_guests": 2,
            "bedrooms": 1,
            "beds": 1,
            "bathrooms": 1.0,
            "base_price_per_night": 100.00,
            "currency": "USD",
            "cleaning_fee": 15.00,
            "service_fee_pct": 10.00,
            "cancellation_policy": "moderate",
            "min_stay_nights": 1,
            "instant_book": True,
        }

        prop = HostService.create_property(property_data, owner_user_id=host.id, owner_org_id=None)
        db.session.commit()

        # No inventory is auto-created anymore (approved lifecycle); the host
        # must configure a RoomType explicitly before the property can hold a
        # booking.
        rt = RoomType(
            property_id=prop.id,
            name="Standard Room",
            description="Default room type for this property",
            max_guests=prop.max_guests,
            bedrooms=prop.bedrooms,
            beds=prop.beds,
            bathrooms=prop.bathrooms,
            base_price_per_night=prop.base_price_per_night,
            currency=prop.currency,
            cleaning_fee=prop.cleaning_fee,
            service_fee_pct=prop.service_fee_pct,
            total_units=5,
            is_active=True,
        )
        db.session.add(rt)
        db.session.commit()

        # A property is bookable only after approval: HostService.create_property
        # produces status="pending_review"/is_verified=False; promote it through
        # the moderation-approval outcome so the property is in a valid bookable
        # domain state (same fields moderation_service.approve_property sets).
        prop.status = "published"
        prop.is_verified = True
        prop.verification_status = "verified"
        prop.is_active = True
        db.session.commit()

        # Check availability originally (should be 5)
        today = date.today()
        tomorrow = today + timedelta(days=1)
        avail = HostService.available_units(rt.id, today, tomorrow)
        assert avail == 5

        # Create booking for 1 unit
        booking, error = BookingService.create_booking(
            property_id=prop.id,
            guest_user_id=guest.id,
            host_user_id=host.id,
            check_in=today,
            check_out=tomorrow,
            num_guests=2,
            guest_name="Test Guest",
            guest_email="guest_test@example.com",
            room_type_id=rt.id
        )
        assert error is None
        assert booking is not None
        assert booking.room_type_id == rt.id

        # Availability should now be 4 (since pending booking holds inventory)
        avail = HostService.available_units(rt.id, today, tomorrow)
        assert avail == 4

        # Add an inventory block for 2 units
        block = InventoryBlock(
            room_type_id=rt.id,
            date_range_start=today,
            date_range_end=tomorrow,
            units_blocked=2,
            reason="MAINTENANCE" # Enforced by InventoryBlockReason enum
        )
        db.session.add(block)
        db.session.commit()

        # Availability should now be 2 (5 - 1 booking - 2 blocked)
        avail = HostService.available_units(rt.id, today, tomorrow)
        assert avail == 2

        # Re-check calendar snapshot
        snapshot = HostService.get_property_calendar_snapshot(
            property_id=prop.id,
            start_date=today,
            end_date=today
        )
        assert len(snapshot["days"]) == 1
        day = snapshot["days"][0]
        # Still available because avail = 2 > 0
        assert day["status"] == "available"

        # Block another 2 units (total 4 units blocked, 1 unit booked, total 5/5)
        block2 = InventoryBlock(
            room_type_id=rt.id,
            date_range_start=today,
            date_range_end=tomorrow,
            units_blocked=2,
            reason="MAINTENANCE"
        )
        db.session.add(block2)
        db.session.commit()

        avail = HostService.available_units(rt.id, today, tomorrow)
        assert avail == 0

        # A fully-consumed day is "blocked" (with a block reason) while the inventory is
        # only HELD: the booking is PENDING_PAYMENT and its unit is held by a
        # temporary_hold InventoryBlock, not an active/confirmed booking. Per
        # Implement/booking_flow.md, HELD is a distinct state from BOOKED (CONFIRMED);
        # the snapshot classifies a day as "booked" only when an active/confirmed
        # booking overlaps it.
        snapshot = HostService.get_property_calendar_snapshot(
            property_id=prop.id,
            start_date=today,
            end_date=today
        )
        day = snapshot["days"][0]
        assert day["status"] == "blocked"
        assert day["blocked_reason"] in ("temporary_hold", "MAINTENANCE")
