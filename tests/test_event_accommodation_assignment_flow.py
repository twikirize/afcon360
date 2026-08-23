"""End-to-end tests for event-accommodation assignment completion flow."""

import uuid
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from flask import url_for

from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.models.booking_registration_link import BookingRegistrationLink
from app.accommodation.models.guest_registration import GuestRegistration
from app.accommodation.models.property import Property, AccommodationCancellationPolicy
from app.accommodation.services.booking_registration_link_service import BookingRegistrationLinkService
from app.accommodation.services.registration_service import RegistrationService
from app.events.models import Event, EventAssignment, EventRegistration
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
        kyc_level=2,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def test_guest_user(test_db):
    """Create a minimal guest user."""
    user = User(
        email=f"guest-{uuid.uuid4().hex[:6]}@example.com",
        username=f"guest-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        kyc_level=2,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def test_property(test_db, test_host_user):
    """Create a minimal test property owned by test_host_user."""
    prop = Property(
        title="Test Property",
        slug=f"test-property-{uuid.uuid4().hex[:8]}",
        description="A test property for automated booking tests.",
        address_line1="123 Test Street",
        city="Kampala",
        country="UG",
        status="active",
        is_verified=True,
        is_active=True,
        base_price_per_night=Decimal("100.00"),
        currency="USD",
        max_guests=4,
        instant_book=True,
        cancellation_policy=AccommodationCancellationPolicy.FLEXIBLE.value,
        owner_user_id=test_host_user.id,
    )
    db.session.add(prop)
    db.session.commit()
    return prop


@pytest.fixture
def event_with_booking(app, test_host_user, test_property):
    """Create an event with an accommodation booking. Returns IDs to avoid detached instances."""
    with app.app_context():
        unique_slug = f"test-event-{uuid.uuid4().hex[:8]}"
        event = Event(
            name="Test Event",
            slug=unique_slug,
            start_date=datetime.now(timezone.utc) + timedelta(days=30),
            end_date=datetime.now(timezone.utc) + timedelta(days=35),
            city="Kampala",
            country="UG",
            venue="Test Venue",
            organizer_id=test_host_user.id,
            created_by_id=test_host_user.id,
        )
        db.session.add(event)
        db.session.flush()

        booking = AccommodationBooking(
            guest_user_id=test_host_user.id,
            host_user_id=test_host_user.id,
            booked_by_user_id=test_host_user.id,
            property_id=test_property.id,
            check_in=datetime.now(timezone.utc) + timedelta(days=30),
            check_out=datetime.now(timezone.utc) + timedelta(days=35),
            num_nights=5,
            num_guests=2,
            rooms_requested=1,
            nightly_rate=Decimal("100.00"),
            total_amount=Decimal("500.00"),
            currency="USD",
            status="confirmed",
            payment_status="paid",
            booking_reference=f"ACC-TEST-{uuid.uuid4().hex[:6].upper()}",
        )
        db.session.add(booking)
        db.session.flush()

        # Create shared registration link
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        link = BookingRegistrationLink(
            booking_id=booking.id,
            token_hash=token_hash,
            max_registrants=2,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.session.add(link)
        db.session.commit()

        return {
            "event_id": event.id,
            "booking_id": booking.id,
            "shared_token": token,
            "shared_token_hash": token_hash,
        }


@pytest.fixture
def attendee_registration(app, test_guest_user, event_with_booking):
    """Create an event registration for an attendee."""
    with app.app_context():
        event = db.session.get(Event, event_with_booking["event_id"])
        registration = EventRegistration(
            event_id=event.id,
            user_id=test_guest_user.id,
            full_name="John Doe",
            email="john@example.com",
            status="confirmed",
            registration_ref="ER-TEST-001",
        )
        db.session.add(registration)
        db.session.commit()
        return registration


def _make_assignment_token(assignment, booking):
    """Generate a token and persist its hash on the assignment (mirrors bridge)."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    assignment.acc_link_token_hash = token_hash
    assignment.acc_link_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    db.session.commit()
    return token


# ============================================================================
# TESTS
# ============================================================================

def test_normal_shared_booking_capacity(app, event_with_booking):
    """Normal shared booking: 2 spots -> 0/1/2 registered -> 3rd rejected (409)."""
    with app.app_context():
        booking = db.session.get(AccommodationBooking, event_with_booking["booking_id"])
        token = event_with_booking["shared_token"]

        # 0 registered initially
        assert RegistrationService.active_count(booking.id) == 0

        # Register guest 1
        with app.test_client() as client:
            resp = client.post(
                url_for("accommodation.shared_registration", token=token),
                data={
                    "guest_name": "Alice",
                    "guest_email": "alice@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "700000000",
                    "id_document_type": "passport",
                },
                follow_redirects=True,
            )
        assert resp.status_code == 200
        assert RegistrationService.active_count(booking.id) == 1

        # Register guest 2
        with app.test_client() as client:
            resp = client.post(
                url_for("accommodation.shared_registration", token=token),
                data={
                    "guest_name": "Bob",
                    "guest_email": "bob@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "700000001",
                    "id_document_type": "national_id",
                },
                follow_redirects=True,
            )
        assert resp.status_code == 200
        assert RegistrationService.active_count(booking.id) == 2

        # 3rd guest should be rejected (409)
        with app.test_client() as client:
            resp = client.post(
                url_for("accommodation.shared_registration", token=token),
                data={
                    "guest_name": "Charlie",
                    "guest_email": "charlie@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "700000002",
                    "id_document_type": "passport",
                },
                follow_redirects=True,
            )
        assert resp.status_code == 409
        assert RegistrationService.active_count(booking.id) == 2


def test_event_assignment_completion_at_capacity(app, event_with_booking, attendee_registration):
    """Event assignment: John assigned (incomplete) -> opens link -> completes -> same GuestRegistration.id, status=completed."""
    with app.app_context():
        event = db.session.get(Event, event_with_booking["event_id"])
        booking = db.session.get(AccommodationBooking, event_with_booking["booking_id"])
        registration = attendee_registration

        # Fill booking to capacity via shared link first
        token = event_with_booking["shared_token"]
        with app.test_client() as client:
            client.post(
                url_for("accommodation.shared_registration", token=token),
                data={
                    "guest_name": "Other Guest",
                    "guest_email": "other@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "700000000",
                    "id_document_type": "passport",
                },
            )
        assert RegistrationService.active_count(booking.id) == 1  # 1 of 2

        # Create assignment for John (event coordination slot)
        assignment = EventAssignment(
            event_id=event.id,
            registration_id=registration.id,
            attendee_id=registration.user_id,
            accommodation_booking_id=booking.id,
            status="active",
            assigned_by_id=event.created_by_id,
        )
        db.session.add(assignment)
        db.session.commit()

        # Issue accommodation for assignment (creates event_coordination slot + token)
        from app.events.accommodation_bridge import issue_accommodation_for_assignment
        issue_accommodation_for_assignment(event, registration, booking, assignment)

        # Verify event_coordination slot created (incomplete)
        slot = GuestRegistration.query.filter_by(
            booking_id=booking.id,
            event_assignment_id=assignment.id,
            is_active=True
        ).first()
        assert slot is not None
        assert slot.registration_source == "event_coordination"
        assert slot.status == "in_progress"
        assert slot.guest_name == "John Doe"
        assert slot.guest_email == "john@example.com"
        assert slot.guest_phone is None  # incomplete
        slot_id = slot.id

        # John completes via his attendee-specific token
        completion_token = _make_assignment_token(assignment, booking)
        with app.test_client() as client:
            resp = client.post(
                url_for("accommodation.assignment_completion", token=completion_token),
                data={
                    "guest_name": "John Doe",
                    "guest_email": "john@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "701000000",
                    "id_document_type": "passport",
                },
                follow_redirects=True,
            )
        assert resp.status_code == 200

        # Same GuestRegistration.id retained, status=completed
        slot = db.session.get(GuestRegistration, slot_id)
        assert slot.id == slot_id
        assert slot.status == "completed"
        assert slot.guest_phone == "+256701000000"
        assert slot.is_placeholder is False


def test_full_booking_existing_guest_can_complete(app, event_with_booking, attendee_registration):
    """Full booking (2/2): John is one -> John can complete -> third person rejected."""
    with app.app_context():
        event = db.session.get(Event, event_with_booking["event_id"])
        booking = db.session.get(AccommodationBooking, event_with_booking["booking_id"])
        registration = attendee_registration

        # Fill to capacity: 1 via shared, 1 via event coordination
        token = event_with_booking["shared_token"]
        with app.test_client() as client:
            client.post(
                url_for("accommodation.shared_registration", token=token),
                data={
                    "guest_name": "Other Guest",
                    "guest_email": "other@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "700000000",
                    "id_document_type": "passport",
                },
            )

        # Create assignment for John
        assignment = EventAssignment(
            event_id=event.id,
            registration_id=registration.id,
            attendee_id=registration.user_id,
            accommodation_booking_id=booking.id,
            status="active",
            assigned_by_id=event.created_by_id,
        )
        db.session.add(assignment)
        db.session.commit()

        from app.events.accommodation_bridge import issue_accommodation_for_assignment
        issue_accommodation_for_assignment(event, registration, booking, assignment)

        # Booking is now full (2/2)
        assert RegistrationService.active_count(booking.id) == 2

        # John completes his incomplete slot
        completion_token = _make_assignment_token(assignment, booking)
        with app.test_client() as client:
            resp = client.post(
                url_for("accommodation.assignment_completion", token=completion_token),
                data={
                    "guest_name": "John Doe",
                    "guest_email": "john@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "701000000",
                    "id_document_type": "passport",
                },
                follow_redirects=True,
            )
        assert resp.status_code == 200

        # Third person via shared link rejected
        with app.test_client() as client:
            resp = client.post(
                url_for("accommodation.shared_registration", token=token),
                data={
                    "guest_name": "Third Person",
                    "guest_email": "third@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "700000002",
                    "id_document_type": "passport",
                },
                follow_redirects=True,
            )
        assert resp.status_code == 409


def test_multiple_attendees_distinct_tokens(app, event_with_booking):
    """Multiple attendees: John->token A, Mary->token B; A resolves John only, B resolves Mary only; no rotation."""
    with app.app_context():
        event = db.session.get(Event, event_with_booking["event_id"])
        booking = db.session.get(AccommodationBooking, event_with_booking["booking_id"])

        # Create two registrations
        john = EventRegistration(
            event_id=event.id, user_id=1, full_name="John Doe", email="john@example.com",
            status="confirmed", registration_ref="ER-TEST-001"
        )
        mary = EventRegistration(
            event_id=event.id, user_id=2, full_name="Mary Smith", email="mary@example.com",
            status="confirmed", registration_ref="ER-TEST-002"
        )
        db.session.add_all([john, mary])
        db.session.flush()

        # Create assignments
        john_assignment = EventAssignment(
            event_id=event.id, registration_id=john.id, attendee_id=john.user_id,
            accommodation_booking_id=booking.id, status="active", assigned_by_id=event.created_by_id
        )
        mary_assignment = EventAssignment(
            event_id=event.id, registration_id=mary.id, attendee_id=mary.user_id,
            accommodation_booking_id=booking.id, status="active", assigned_by_id=event.created_by_id
        )
        db.session.add_all([john_assignment, mary_assignment])
        db.session.commit()

        from app.events.accommodation_bridge import issue_accommodation_for_assignment
        issue_accommodation_for_assignment(event, john, booking, john_assignment)
        issue_accommodation_for_assignment(event, mary, booking, mary_assignment)

        # Get tokens
        john_token = _make_assignment_token(john_assignment, booking)
        mary_token = _make_assignment_token(mary_assignment, booking)

        # John's token resolves John's slot only
        with app.test_client() as client:
            resp = client.get(url_for("accommodation.assignment_completion", token=john_token))
        assert resp.status_code == 200
        assert b"John Doe" in resp.data

        # Mary's token resolves Mary's slot only
        with app.test_client() as client:
            resp = client.get(url_for("accommodation.assignment_completion", token=mary_token))
        assert resp.status_code == 200
        assert b"Mary Smith" in resp.data

        # Tokens don't cross-resolve
        with app.test_client() as client:
            resp = client.post(
                url_for("accommodation.assignment_completion", token=john_token),
                data={
                    "guest_name": "John Doe",
                    "guest_email": "john@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "701000000",
                    "id_document_type": "passport",
                },
            )
        assert resp.status_code == 200

        # John's slot updated, Mary's unchanged
        john_slot = GuestRegistration.query.filter_by(
            booking_id=booking.id, event_assignment_id=john_assignment.id
        ).first()
        mary_slot = GuestRegistration.query.filter_by(
            booking_id=booking.id, event_assignment_id=mary_assignment.id
        ).first()
        assert john_slot.status == "completed"
        assert mary_slot.status == "in_progress"  # still incomplete

        # Earlier tokens remain valid (no rotation)
        with app.test_client() as client:
            resp = client.get(url_for("accommodation.assignment_completion", token=john_token))
        assert resp.status_code == 200


def test_reassignment_deactivates_old_slot(app, event_with_booking, attendee_registration):
    """Reassignment: John->Hotel B1; John's slot inactive, Mary active, capacity correct, John's token invalid."""
    with app.app_context():
        event = db.session.get(Event, event_with_booking["event_id"])
        booking_a = db.session.get(AccommodationBooking, event_with_booking["booking_id"])
        registration = attendee_registration

        # Create booking B
        prop_b = Property.query.filter(Property.id != booking_a.property_id).first()
        if not prop_b:
            prop_b = Property(
                title="Hotel B",
                owner_id=event.created_by_id,
                status="approved",
                property_type="hotel",
            )
            db.session.add(prop_b)
            db.session.flush()

        booking_b = AccommodationBooking(
            guest_user_id=event.created_by_id,
            host_user_id=event.created_by_id,
            booked_by_user_id=event.created_by_id,
            property_id=prop_b.id,
            check_in=booking_a.check_in,
            check_out=booking_a.check_out,
            num_nights=5,
            num_guests=1,
            rooms_requested=1,
            nightly_rate=Decimal("100.00"),
            total_amount=Decimal("500.00"),
            currency="USD",
            status="confirmed",
            payment_status="paid",
            booking_reference=f"ACC-TEST-{uuid.uuid4().hex[:6].upper()}",
        )
        db.session.add(booking_b)
        db.session.commit()

        # Initial assignment to booking A
        assignment = EventAssignment(
            event_id=event.id,
            registration_id=registration.id,
            attendee_id=registration.user_id,
            accommodation_booking_id=booking_a.id,
            status="active",
            assigned_by_id=event.created_by_id,
        )
        db.session.add(assignment)
        db.session.commit()

        from app.events.accommodation_bridge import issue_accommodation_for_assignment
        issue_accommodation_for_assignment(event, registration, booking_a, assignment)
        john_token_a = _make_assignment_token(assignment, booking_a)

        # Verify slot in booking A
        slot_a = GuestRegistration.query.filter_by(
            booking_id=booking_a.id, event_assignment_id=assignment.id, is_active=True
        ).first()
        assert slot_a is not None
        assert slot_a.is_active

        # Reassign to booking B (via service)
        from app.events.guest_coordination_service import GuestCoordinationService
        from app.identity.models.user import User
        actor = User.query.get(event.created_by_id)
        GuestCoordinationService.assign_accommodation(event, actor, registration.registration_ref, booking_b.booking_reference)

        # Old slot in A deactivated
        slot_a = db.session.get(GuestRegistration, slot_a.id)
        assert slot_a.is_active is False
        assert slot_a.removed_reason == "reassigned"

        # New slot in B active
        slot_b = GuestRegistration.query.filter_by(
            booking_id=booking_b.id, event_assignment_id=assignment.id, is_active=True
        ).first()
        assert slot_b is not None
        assert slot_b.is_active

        # Capacity: booking A freed, booking B occupied
        assert RegistrationService.active_count(booking_a.id) == 0
        assert RegistrationService.active_count(booking_b.id) == 1

        # Old token invalid (404)
        with app.test_client() as client:
            resp = client.get(url_for("accommodation.assignment_completion", token=john_token_a))
        assert resp.status_code in (404, 410)


def test_cancellation_frees_capacity(app, event_with_booking, attendee_registration):
    """Cancellation: slot inactive, capacity freed, token unusable."""
    with app.app_context():
        event = db.session.get(Event, event_with_booking["event_id"])
        booking = db.session.get(AccommodationBooking, event_with_booking["booking_id"])
        registration = attendee_registration

        assignment = EventAssignment(
            event_id=event.id,
            registration_id=registration.id,
            attendee_id=registration.user_id,
            accommodation_booking_id=booking.id,
            status="active",
            assigned_by_id=event.created_by_id,
        )
        db.session.add(assignment)
        db.session.commit()

        from app.events.accommodation_bridge import issue_accommodation_for_assignment
        issue_accommodation_for_assignment(event, registration, booking, assignment)
        token = _make_assignment_token(assignment, booking)

        slot = GuestRegistration.query.filter_by(
            booking_id=booking.id, event_assignment_id=assignment.id, is_active=True
        ).first()
        assert slot is not None
        slot_id = slot.id

        # Cancel
        from app.events.guest_coordination_service import GuestCoordinationService
        from app.identity.models.user import User
        actor = User.query.get(event.created_by_id)
        GuestCoordinationService.cancel(event, actor, registration.registration_ref, "accommodation")

        # Slot inactive
        slot = db.session.get(GuestRegistration, slot_id)
        assert slot.is_active is False
        assert slot.removed_reason == "assignment cancelled"

        # Capacity freed
        assert RegistrationService.active_count(booking.id) == 0

        # Token unusable
        with app.test_client() as client:
            resp = client.get(url_for("accommodation.assignment_completion", token=token))
        assert resp.status_code in (404, 410)


def test_token_authorization_isolation(app, event_with_booking):
    """John's token cannot modify Mary's registration."""
    with app.app_context():
        event = db.session.get(Event, event_with_booking["event_id"])
        booking = db.session.get(AccommodationBooking, event_with_booking["booking_id"])

        john = EventRegistration(
            event_id=event.id, user_id=1, full_name="John Doe", email="john@example.com",
            status="confirmed", registration_ref="ER-TEST-001"
        )
        mary = EventRegistration(
            event_id=event.id, user_id=2, full_name="Mary Smith", email="mary@example.com",
            status="confirmed", registration_ref="ER-TEST-002"
        )
        db.session.add_all([john, mary])
        db.session.flush()

        john_assignment = EventAssignment(
            event_id=event.id, registration_id=john.id, attendee_id=john.user_id,
            accommodation_booking_id=booking.id, status="active", assigned_by_id=event.created_by_id
        )
        mary_assignment = EventAssignment(
            event_id=event.id, registration_id=mary.id, attendee_id=mary.user_id,
            accommodation_booking_id=booking.id, status="active", assigned_by_id=event.created_by_id
        )
        db.session.add_all([john_assignment, mary_assignment])
        db.session.commit()

        from app.events.accommodation_bridge import issue_accommodation_for_assignment
        issue_accommodation_for_assignment(event, john, booking, john_assignment)
        issue_accommodation_for_assignment(event, mary, booking, mary_assignment)

        john_token = _make_assignment_token(john_assignment, booking)
        mary_token = _make_assignment_token(mary_assignment, booking)

        # John tries to POST to Mary's slot using his token - should not work
        with app.test_client() as client:
            resp = client.post(
                url_for("accommodation.assignment_completion", token=john_token),
                data={
                    "guest_name": "Mary Smith",
                    "guest_email": "mary@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "701000000",
                    "id_document_type": "passport",
                },
                follow_redirects=True,
            )
        # Should update John's slot, not Mary's
        assert resp.status_code == 200

        john_slot = GuestRegistration.query.filter_by(
            booking_id=booking.id, event_assignment_id=john_assignment.id
        ).first()
        mary_slot = GuestRegistration.query.filter_by(
            booking_id=booking.id, event_assignment_id=mary_assignment.id
        ).first()

        # John's slot got updated (his token -> his slot)
        assert john_slot.guest_name == "Mary Smith"  # form allows name change but email is read-only
        # Mary's slot unchanged
        assert mary_slot.guest_name == "Mary Smith"
        assert mary_slot.guest_email == "mary@example.com"


def test_shared_link_rejects_unknown_at_capacity(app, event_with_booking, attendee_registration):
    """Shared link still rejects unknown third party at capacity."""
    with app.app_context():
        event = db.session.get(Event, event_with_booking["event_id"])
        booking = db.session.get(AccommodationBooking, event_with_booking["booking_id"])
        registration = attendee_registration

        # Fill capacity: 1 shared + 1 event coordination
        token = event_with_booking["shared_token"]
        with app.test_client() as client:
            client.post(
                url_for("accommodation.shared_registration", token=token),
                data={
                    "guest_name": "Shared Guest",
                    "guest_email": "shared@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "700000000",
                    "id_document_type": "passport",
                },
            )

        assignment = EventAssignment(
            event_id=event.id,
            registration_id=registration.id,
            attendee_id=registration.user_id,
            accommodation_booking_id=booking.id,
            status="active",
            assigned_by_id=event.created_by_id,
        )
        db.session.add(assignment)
        db.session.commit()

        from app.events.accommodation_bridge import issue_accommodation_for_assignment
        issue_accommodation_for_assignment(event, registration, booking, assignment)

        # Booking full
        assert RegistrationService.active_count(booking.id) == 2

        # Unknown third party via shared link rejected
        with app.test_client() as client:
            resp = client.post(
                url_for("accommodation.shared_registration", token=token),
                data={
                    "guest_name": "Unknown",
                    "guest_email": "unknown@example.com",
                    "guest_phone_country_code": "+256",
                    "guest_phone_national": "700000001",
                    "id_document_type": "passport",
                },
                follow_redirects=True,
            )
        assert resp.status_code == 409


def test_notification_email_content(app, event_with_booking, attendee_registration):
    """Email contains event, property, dates, booking ref, guest name, completion URL, correct CTA, no N/A/UGX 0/TBD."""
    with app.app_context():
        event = db.session.get(Event, event_with_booking["event_id"])
        booking = db.session.get(AccommodationBooking, event_with_booking["booking_id"])
        registration = attendee_registration

        assignment = EventAssignment(
            event_id=event.id,
            registration_id=registration.id,
            attendee_id=registration.user_id,
            accommodation_booking_id=booking.id,
            status="active",
            assigned_by_id=event.created_by_id,
        )
        db.session.add(assignment)
        db.session.commit()

        from app.events.accommodation_bridge import issue_accommodation_for_assignment
        issue_accommodation_for_assignment(event, registration, booking, assignment)

        # Check notification was created with correct type
        from app.notifications.models import Notification, NotificationType
        notification = Notification.query.filter_by(
            type=NotificationType.EVENT_ACCOMMODATION_ASSIGNED,
            email=registration.email
        ).first()
        assert notification is not None
        assert notification.module == "accommodation"
        assert notification.link is not None
        assert "assignment_completion" in notification.link

        # Check context has required fields
        ctx = notification.context
        assert ctx.get("event_name") == "Test Event"
        assert ctx.get("property_title") == booking.accommodation_property.title
        assert ctx.get("check_in") is not None
        assert ctx.get("check_out") is not None
        assert ctx.get("booking_reference") == booking.booking_reference
        assert ctx.get("guest_name") == "John Doe"

        # Render template and verify no bogus values
        from flask import render_template_string
        with app.test_request_context():
            html = render_template_string(
                open("templates/notifications/email/event_accommodation_assigned.html").read(),
                **ctx,
                guest_name=ctx.get("guest_name"),
                link=notification.link
            )
        assert "N/A" not in html
        assert "UGX 0" not in html
        assert "TBD" not in html
        assert "View Booking Pass" not in html
        assert "Complete your accommodation details" in html
        assert "Test Event" in html
        assert booking.accommodation_property.title in html
        assert booking.booking_reference in html
        assert notification.link in html