"""Tests for attendee-initiated accommodation booking orchestration."""

import uuid
from datetime import date, timedelta, timezone
from decimal import Decimal

import pytest
from flask import url_for

from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus
from app.accommodation.models.property import Property, AccommodationPropertyStatus
from app.accommodation.models.booking_policy import PropertyBookingPolicy
from app.events.models import Event, EventRegistration, EventAssignment, TicketType
from app.events.accommodation_booking_service import AttendeeAccommodationBookingService, AttendeeAccommodationBookingError
from app.extensions import db
from app.identity.models.user import User


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def test_host_user(test_db):
    """Create a minimal host user."""
    user = User(
        email=f"host-{uuid.uuid4().hex[:6]}@example.com",
        username=f"host-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        is_verified=True,
        is_active=True,
        kyc_level=2,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def test_guest_user(test_db):
    """Create a minimal guest user (attendee)."""
    user = User(
        email=f"guest-{uuid.uuid4().hex[:6]}@example.com",
        username=f"guest-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        is_verified=True,
        is_active=True,
        kyc_level=2,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def test_organizer_user(test_db):
    """Create an organizer user."""
    user = User(
        email=f"organizer-{uuid.uuid4().hex[:6]}@example.com",
        username=f"organizer-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        is_verified=True,
        is_active=True,
        kyc_level=2,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def test_property(test_db, test_host_user):
    """Create a test property with booking policy allowing pay_now and pay_on_arrival."""
    prop = Property(
        title="Test Hotel",
        slug=f"test-hotel-{uuid.uuid4().hex[:8]}",
        description="A test hotel for automated booking tests.",
        address_line1="123 Test Street",
        city="Kampala",
        country="UG",
        status=AccommodationPropertyStatus.ACTIVE.value,
        is_verified=True,
        is_active=True,
        base_price_per_night=Decimal("100.00"),
        currency="USD",
        max_guests=4,
        instant_book=True,
        owner_user_id=test_host_user.id,
    )
    db.session.add(prop)
    db.session.flush()
    
    # Create booking policy for the property
    policy = PropertyBookingPolicy(
        property_id=prop.id,
        cancellation_policy="flexible",
        free_cancel_hours=24,
        allow_pay_now=True,
        allow_pay_on_arrival=True,
        allow_pay_at_checkout=True,
        allow_deposit_payment=True,
        deposit_percentage=30,
        require_payment_guarantee=False,
        require_guest_identity=False,
        is_active=True,
    )
    db.session.add(policy)
    db.session.commit()
    return prop


@pytest.fixture
def test_event(test_db, test_organizer_user):
    """Create a test event."""
    event = Event(
        name="Test Event",
        slug=f"test-event-{uuid.uuid4().hex[:8]}",
        start_date=date.today() + timedelta(days=30),
        end_date=date.today() + timedelta(days=35),
        city="Kampala",
        country="UG",
        venue="Test Venue",
        organizer_id=test_organizer_user.id,
        created_by_id=test_organizer_user.id,
        current_owner_type="individual",
        current_owner_id=test_organizer_user.id,
        created_by_type="individual",
        created_by_entity_id=test_organizer_user.id,
    )
    db.session.add(event)
    db.session.flush()
    
    # Create a ticket type
    ticket_type = TicketType(
        event_id=event.id,
        name="General",
        price=0,
        capacity=100,
        is_active=True,
    )
    db.session.add(ticket_type)
    db.session.flush()
    
    return {
        "event": event,
        "ticket_type_id": ticket_type.id,
    }


@pytest.fixture
def attendee_registration(test_db, test_guest_user, test_event):
    """Create an event registration for an attendee."""
    event = test_event["event"]
    registration = EventRegistration(
        event_id=event.id,
        ticket_type_id=test_event["ticket_type_id"],
        user_id=test_guest_user.id,
        full_name="John Doe",
        email="john@example.com",
        phone="+256700000000",
        nationality="UG",
        status="confirmed",
    )
    registration.generate_refs(event.slug, 1)
    db.session.add(registration)
    db.session.commit()
    return registration


# ============================================================================
# TESTS
# ============================================================================

class TestAttendeeAccommodationBookingService:
    """Test the AttendeeAccommodationBookingService orchestration."""
    
    def test_list_available_properties(self, app, test_property, test_event, attendee_registration):
        """Test listing available properties for event dates."""
        with app.app_context():
            event = test_event["event"]
            registration = attendee_registration
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            properties = AttendeeAccommodationBookingService.list_available_properties_for_event(
                event, check_in, check_out, num_guests=2, rooms_requested=1
            )
            
            assert len(properties) >= 1
            prop = properties[0]
            assert prop["property_id"] == test_property.id
            assert prop["title"] == test_property.title
            assert "pay_now" in prop["payment_timings"]
            assert "pay_on_arrival" in prop["payment_timings"]
            assert "pay_at_checkout" in prop["payment_timings"]
    
    def test_create_booking_pay_now(self, app, test_property, test_event, attendee_registration):
        """Test creating a booking with pay_now timing."""
        with app.app_context():
            event = test_event["event"]
            registration = attendee_registration
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            result = AttendeeAccommodationBookingService.create_booking_for_attendee(
                event=event,
                registration=registration,
                property_id=test_property.id,
                check_in=check_in,
                check_out=check_out,
                num_guests=2,
                rooms_requested=1,
                payment_timing="pay_now",
                payment_method="wallet",
            )
            
            assert result.booking is not None
            assert result.booking.property_id == test_property.id
            assert result.booking.check_in == check_in
            assert result.booking.check_out == check_out
            assert result.booking.num_guests == 2
            assert result.booking.rooms_requested == 1
            assert result.booking.payment_timing == "pay_now"
            assert result.booking.context_type == "event"
            assert result.booking.context_id == str(event.public_id)
            assert result.booking.booking_type == "event_assigned"
            assert result.assignment.accommodation_booking_id == result.booking.id
            # For pay_now, payment is required before confirmation
            assert result.payment_required is True
            assert result.required_amount is not None
            assert result.required_amount == result.booking.total_amount
    
    def test_create_booking_pay_on_arrival(self, app, test_property, test_event, attendee_registration):
        """Test creating a booking with pay_on_arrival timing (no upfront payment required)."""
        with app.app_context():
            event = test_event["event"]
            registration = attendee_registration
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            result = AttendeeAccommodationBookingService.create_booking_for_attendee(
                event=event,
                registration=registration,
                property_id=test_property.id,
                check_in=check_in,
                check_out=check_out,
                num_guests=2,
                rooms_requested=1,
                payment_timing="pay_on_arrival",
            )
            
            assert result.booking is not None
            assert result.booking.payment_timing == "pay_on_arrival"
            # For pay_on_arrival, no upfront payment required for confirmation
            assert result.payment_required is False
    
    def test_create_booking_pay_at_checkout(self, app, test_property, test_event, attendee_registration):
        """Test creating a booking with pay_at_checkout timing (no upfront payment required)."""
        with app.app_context():
            event = test_event["event"]
            registration = attendee_registration
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            result = AttendeeAccommodationBookingService.create_booking_for_attendee(
                event=event,
                registration=registration,
                property_id=test_property.id,
                check_in=check_in,
                check_out=check_out,
                num_guests=2,
                rooms_requested=1,
                payment_timing="pay_at_checkout",
            )
            
            assert result.booking is not None
            assert result.booking.payment_timing == "pay_at_checkout"
            # For pay_at_checkout, no upfront payment required for confirmation
            assert result.payment_required is False
    
    def test_create_booking_deposit(self, app, test_property, test_event, attendee_registration):
        """Test creating a booking with deposit timing."""
        with app.app_context():
            event = test_event["event"]
            registration = attendee_registration
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            result = AttendeeAccommodationBookingService.create_booking_for_attendee(
                event=event,
                registration=registration,
                property_id=test_property.id,
                check_in=check_in,
                check_out=check_out,
                num_guests=2,
                rooms_requested=1,
                payment_timing="deposit",
            )
            
            assert result.booking is not None
            assert result.booking.payment_timing == "deposit"
            # Deposit percentage is 30%, so 30% of total required
            expected_deposit = (result.booking.total_amount * Decimal("30")) / Decimal("100")
            assert result.payment_required is True
            assert result.required_amount == expected_deposit
    
    def test_create_booking_invoice(self, app, test_property, test_event, attendee_registration):
        """Test creating a booking with invoice timing (no upfront payment required)."""
        with app.app_context():
            event = test_event["event"]
            registration = attendee_registration
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            result = AttendeeAccommodationBookingService.create_booking_for_attendee(
                event=event,
                registration=registration,
                property_id=test_property.id,
                check_in=check_in,
                check_out=check_out,
                num_guests=2,
                rooms_requested=1,
                payment_timing="invoice",
            )
            
            assert result.booking is not None
            assert result.booking.payment_timing == "invoice"
            # For invoice, no upfront payment required for confirmation
            assert result.payment_required is False
    
    def test_create_booking_creates_guest_slot(self, app, test_property, test_event, attendee_registration):
        """Test that booking creation creates a guest slot via AccommodationCoordinationContract."""
        with app.app_context():
            event = test_event["event"]
            registration = attendee_registration
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            result = AttendeeAccommodationBookingService.create_booking_for_attendee(
                event=event,
                registration=registration,
                property_id=test_property.id,
                check_in=check_in,
                check_out=check_out,
                num_guests=2,
                rooms_requested=1,
            )
            
            # Verify guest slot was created
            from app.accommodation.models.guest_registration import GuestRegistration
            slot = GuestRegistration.query.filter_by(
                booking_id=result.booking.id,
                event_assignment_id=result.assignment.id,
                is_active=True,
            ).first()
            
            assert slot is not None
            assert slot.guest_name == "John Doe"
            assert slot.guest_email == "john@example.com"
            assert slot.registration_source == "event_coordination"
            assert slot.status == "in_progress"  # incomplete until attendee completes
    
    def test_create_booking_links_event_assignment(self, app, test_property, test_event, attendee_registration):
        """Test that booking is linked to EventAssignment."""
        with app.app_context():
            event = test_event["event"]
            registration = attendee_registration
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            result = AttendeeAccommodationBookingService.create_booking_for_attendee(
                event=event,
                registration=registration,
                property_id=test_property.id,
                check_in=check_in,
                check_out=check_out,
            )
            
            # Verify assignment was created/updated
            assignment = EventAssignment.query.filter_by(
                event_id=event.id,
                registration_id=registration.id,
            ).first()
            
            assert assignment is not None
            assert assignment.accommodation_booking_id == result.booking.id
            assert assignment.registration_id == registration.id
            assert assignment.attendee_id == registration.user_id
    
    def test_get_booking_requirements(self, app, test_property, test_event, attendee_registration):
        """Test getting booking requirements for frontend display."""
        with app.app_context():
            event = test_event["event"]
            registration = attendee_registration
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            # Create a booking first
            result = AttendeeAccommodationBookingService.create_booking_for_attendee(
                event=event,
                registration=registration,
                property_id=test_property.id,
                check_in=check_in,
                check_out=check_out,
                payment_timing="pay_now",
            )
            
            # Get requirements
            requirements = AttendeeAccommodationBookingService.get_booking_requirements(event, registration)
            
            assert requirements["has_booking"] is True
            assert "can_confirm" in requirements
            assert "can_check_in" in requirements
            assert "payment_policy" in requirements
            assert "financial_summary" in requirements
    
    def test_cancel_attendee_booking(self, app, test_property, test_event, attendee_registration):
        """Test cancelling an attendee's booking."""
        with app.app_context():
            event = test_event["event"]
            registration = attendee_registration
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            # Create a booking
            result = AttendeeAccommodationBookingService.create_booking_for_attendee(
                event=event,
                registration=registration,
                property_id=test_property.id,
                check_in=check_in,
                check_out=check_out,
            )
            
            booking_id = result.booking.id
            
            # Cancel the booking
            success = AttendeeAccommodationBookingService.cancel_attendee_booking(
                event=event,
                registration=registration,
                actor_user_id=test_organizer_user.id,
                reason="Attendee cancelled",
            )
            
            assert success is True
            
            # Verify booking is cancelled
            booking = db.session.get(AccommodationBooking, booking_id)
            assert booking.status == AccommodationBookingStatus.CANCELLED.value
            
            # Verify assignment link is cleared
            assignment = EventAssignment.query.filter_by(
                event_id=event.id,
                registration_id=registration.id,
            ).first()
            assert assignment.accommodation_booking_id is None
    
    def test_rejects_unconfirmed_registration(self, app, test_property, test_event, test_guest_user):
        """Test that unconfirmed registrations cannot book accommodation."""
        with app.app_context():
            event = test_event["event"]
            
            # Create unconfirmed registration
            registration = EventRegistration(
                event_id=event.id,
                ticket_type_id=test_event["ticket_type_id"],
                user_id=test_guest_user.id,
                full_name="Jane Doe",
                email="jane@example.com",
                status="pending_payment",  # NOT confirmed
            )
            registration.generate_refs(event.slug, 2)
            db.session.add(registration)
            db.session.commit()
            
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            with pytest.raises(AttendeeAccommodationBookingError) as exc_info:
                AttendeeAccommodationBookingService.create_booking_for_attendee(
                    event=event,
                    registration=registration,
                    property_id=test_property.id,
                    check_in=check_in,
                    check_out=check_out,
                )
            
            assert exc_info.value.code == "REGISTRATION_NOT_CONFIRMED"
    
    def test_rejects_wrong_event_registration(self, app, test_property, test_db, test_guest_user):
        """Test that registration from different event cannot book."""
        with app.app_context():
            # Create another event
            other_event = Event(
                name="Other Event",
                slug=f"other-event-{uuid.uuid4().hex[:8]}",
                start_date=date.today() + timedelta(days=30),
                end_date=date.today() + timedelta(days=35),
                city="Kampala",
                country="UG",
                venue="Other Venue",
                organizer_id=test_guest_user.id,
                created_by_id=test_guest_user.id,
            )
            db.session.add(other_event)
            db.session.flush()
            
            ticket_type = TicketType(
                event_id=other_event.id,
                name="General",
                price=0,
                capacity=100,
                is_active=True,
            )
            db.session.add(ticket_type)
            db.session.flush()
            
            registration = EventRegistration(
                event_id=other_event.id,
                ticket_type_id=ticket_type.id,
                user_id=test_guest_user.id,
                full_name="John Doe",
                email="john@example.com",
                status="confirmed",
            )
            registration.generate_refs(other_event.slug, 1)
            db.session.add(registration)
            db.session.commit()
            
            # Try to book using registration from other_event for test_event
            event = Event.query.filter_by(slug="test-event").first()
            if not event:
                # Create test_event if not exists
                event = Event(
                    name="Test Event",
                    slug="test-event",
                    start_date=date.today() + timedelta(days=30),
                    end_date=date.today() + timedelta(days=35),
                    city="Kampala",
                    country="UG",
                    venue="Test Venue",
                    organizer_id=test_guest_user.id,
                    created_by_id=test_guest_user.id,
                )
                db.session.add(event)
                db.session.commit()
            
            check_in = date.today() + timedelta(days=30)
            check_out = date.today() + timedelta(days=32)
            
            with pytest.raises(AttendeeAccommodationBookingError) as exc_info:
                AttendeeAccommodationBookingService.create_booking_for_attendee(
                    event=event,
                    registration=registration,
                    property_id=test_property.id,
                    check_in=check_in,
                    check_out=check_out,
                )
            
            assert exc_info.value.code == "REGISTRATION_EVENT_MISMATCH"


class TestAttendeeAccommodationBookingAPI:
    """Test the API endpoints for attendee accommodation booking."""
    
    def test_available_properties_api(self, client, app, test_property, test_event, attendee_registration):
        """Test the available properties API endpoint."""
        with app.app_context():
            event = test_event["event"]
            check_in = (date.today() + timedelta(days=30)).isoformat()
            check_out = (date.today() + timedelta(days=32)).isoformat()
            
            with client.session_transaction() as sess:
                sess['user_id'] = attendee_registration.user_id
                sess['_fresh'] = True
            
            resp = client.get(
                url_for('events.api_attendee_accommodation_available_properties', slug=event.slug),
                query_string={
                    'check_in': check_in,
                    'check_out': check_out,
                    'num_guests': 2,
                    'rooms_requested': 1,
                }
            )
            
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert len(data['properties']) >= 1
    
    def test_book_accommodation_api(self, client, app, test_property, test_event, attendee_registration):
        """Test the book accommodation API endpoint."""
        with app.app_context():
            event = test_event["event"]
            check_in = (date.today() + timedelta(days=30)).isoformat()
            check_out = (date.today() + timedelta(days=32)).isoformat()
            
            with client.session_transaction() as sess:
                sess['user_id'] = attendee_registration.user_id
                sess['_fresh'] = True
            
            resp = client.post(
                url_for('events.api_attendee_accommodation_book', slug=event.slug),
                json={
                    'property_id': test_property.id,
                    'check_in': check_in,
                    'check_out': check_out,
                    'num_guests': 2,
                    'rooms_requested': 1,
                    'payment_timing': 'pay_now',
                }
            )
            
            assert resp.status_code == 201
            data = resp.get_json()
            assert data['success'] is True
            assert data['booking']['property_id'] == test_property.id
            assert data['booking']['payment_timing'] == 'pay_now'
            assert data['booking']['payment_required'] is True
    
    def test_book_accommodation_pay_on_arrival_api(self, client, app, test_property, test_event, attendee_registration):
        """Test booking with pay_on_arrival - no upfront payment required."""
        with app.app_context():
            event = test_event["event"]
            check_in = (date.today() + timedelta(days=30)).isoformat()
            check_out = (date.today() + timedelta(days=32)).isoformat()
            
            with client.session_transaction() as sess:
                sess['user_id'] = attendee_registration.user_id
                sess['_fresh'] = True
            
            resp = client.post(
                url_for('events.api_attendee_accommodation_book', slug=event.slug),
                json={
                    'property_id': test_property.id,
                    'check_in': check_in,
                    'check_out': check_out,
                    'num_guests': 2,
                    'rooms_requested': 1,
                    'payment_timing': 'pay_on_arrival',
                }
            )
            
            assert resp.status_code == 201
            data = resp.get_json()
            assert data['success'] is True
            assert data['booking']['payment_timing'] == 'pay_on_arrival'
            assert data['booking']['payment_required'] is False
    
    def test_book_accommodation_requires_auth(self, client, app, test_property, test_event):
        """Test that booking requires authentication."""
        with app.app_context():
            event = test_event["event"]
            check_in = (date.today() + timedelta(days=30)).isoformat()
            check_out = (date.today() + timedelta(days=32)).isoformat()
            
            # No login
            resp = client.post(
                url_for('events.api_attendee_accommodation_book', slug=event.slug),
                json={
                    'property_id': test_property.id,
                    'check_in': check_in,
                    'check_out': check_out,
                    'num_guests': 2,
                }
            )
            
            # Should be redirected to login (302) or return 401
            assert resp.status_code in (302, 401, 403)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])