import pytest
from datetime import date, timedelta
from app.extensions import db
from app.accommodation.models.property import Property, RoomType, InventoryBlock, AccommodationPropertyType, AccommodationCancellationPolicy
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus, AccommodationPaymentStatus
from app.accommodation.services.host_service import HostService
from app.accommodation.services.booking_service import BookingService
from app.identity.models.user import User

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

def test_room_type_auto_creation_and_update(app):
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
            "property_type": "hotel_room",
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

        # Create property - should auto-create RoomType regardless of whether owner_org_id is set
        prop = HostService.create_property(property_data, owner_user_id=host.id, owner_org_id=123)
        db.session.commit()

        assert prop.id is not None
        
        # Verify RoomType was auto-created
        rts = RoomType.query.filter_by(property_id=prop.id).all()
        assert len(rts) == 1
        rt = rts[0]
        assert rt.name == "Standard Room"
        assert rt.total_units == 1
        assert rt.base_price_per_night == 150.00
        assert rt.max_guests == 4

        # Update Property
        update_data = property_data.copy()
        update_data["title"] = "Marriott Nakasero Updated"
        update_data["max_guests"] = 5
        update_data["base_price_per_night"] = 180.00

        HostService.update_property(prop, update_data)
        db.session.commit()

        # Verify RoomType synced updated fields
        db.session.refresh(rt)
        assert rt.max_guests == 5
        assert rt.base_price_per_night == 180.00

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
            "property_type": "hotel_room",
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

        rt = RoomType.query.filter_by(property_id=prop.id).first()
        
        # Make total_units = 5 for hotel scenario
        rt.total_units = 5
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

        # Snapshot should show status as "booked" (since total available <= 0 and there is a booking)
        snapshot = HostService.get_property_calendar_snapshot(
            property_id=prop.id,
            start_date=today,
            end_date=today
        )
        day = snapshot["days"][0]
        assert day["status"] == "booked"
