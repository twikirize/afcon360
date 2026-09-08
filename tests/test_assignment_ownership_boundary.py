"""Ownership-boundary tests for the Event <-> Accommodation assignment flow.

Stage 5-1: prove that Events coordinates but does not own accommodation state.

These tests assert that the Events module:
  * never writes GuestRegistration / AccommodationBooking directly
  * routes every guest-slot write through AccommodationCoordinationContract
  * treats EventAssignment.accommodation_booking_id as a coordination ref (no FK)
  * rejects bookings that do not belong to the event
  * creates no wallet / payment / ledger records during assignment
"""

import uuid
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.events.guest_coordination_service import GuestCoordinationService, CoordinationError
from app.accommodation.services.coordination_contract import (
    AccommodationCoordinationContract,
    CoordinationContractError,
)
from app.extensions import db
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus


# Fixtures mirror tests/test_guest_coordination_accommodation.py -----------------

@pytest.fixture
def actor():
    from app.identity.models.user import User

    unique_suffix = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"coord_actor_{unique_suffix}",
        email=f"actor_{unique_suffix}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    user.set_password("Password123!")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def other_actor():
    from app.identity.models.user import User

    unique_suffix = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"other_owner_{unique_suffix}",
        email=f"other_owner_{unique_suffix}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    user.set_password("Password123!")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def event(actor):
    from app.events.models import Event

    unique_slug = f"test-event-{uuid.uuid4().hex[:8]}"
    ev = Event(
        public_id=str(uuid.uuid4()),
        event_ref=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        slug=unique_slug,
        name="Test Event",
        organizer_id=actor.id,
        city="Test City",
        country="UG",
        description="Test event description",
        category="general",
        max_capacity=100,
        registration_fee=Decimal("0.00"),
        currency="USD",
        start_date=datetime.now(timezone.utc).date() - timedelta(days=1),
        end_date=datetime.now(timezone.utc).date() + timedelta(days=2),
        status="pending_approval",
    )
    db.session.add(ev)
    db.session.commit()
    return ev


@pytest.fixture
def ticket_type(event):
    from app.events.models import TicketType

    tt = TicketType(
        event_id=event.id,
        name="General",
        price=Decimal("0.00"),
        capacity=100,
        is_active=True,
    )
    db.session.add(tt)
    db.session.commit()
    return tt


@pytest.fixture
def event_guest():
    from app.events.models import EventGuest

    unique_suffix = uuid.uuid4().hex[:8]
    guest = EventGuest(
        full_name="John Doe",
        email=f"john.doe_{unique_suffix}@example.com",
    )
    db.session.add(guest)
    db.session.commit()
    return guest


@pytest.fixture
def registration(event, ticket_type, event_guest):
    from app.events.models import EventRegistration

    reg = EventRegistration(
        event_id=event.id,
        ticket_type_id=ticket_type.id,
        full_name=event_guest.full_name,
        email=event_guest.email,
        phone=event_guest.phone,
        nationality=event_guest.nationality,
        status="confirmed",
        payment_status="free",
        registration_fee=Decimal("0.00"),
        guest_id=event_guest.id,
        booking_type="self",
    )
    db.session.add(reg)
    seq = int(uuid.uuid4().int % 10 ** 8)
    reg.generate_refs(event_slug=event.slug, sequence=seq)
    db.session.commit()
    return reg


@pytest.fixture
def property_(actor):
    from app.accommodation.models.property import Property

    unique_suffix = uuid.uuid4().hex[:8]
    prop = Property(
        owner_user_id=actor.id,
        title=f"Test Property {unique_suffix}",
        slug=f"test-property-{unique_suffix}",
        description="A test property for coordination tests",
        address_line1="123 Test Street",
        city="Test City",
        state="Test State",
        country="UG",
        base_price_per_night=Decimal("100.00"),
        max_guests=2,
        status="active",
        is_verified=True,
        is_active=True,
        visibility="public",
    )
    db.session.add(prop)
    db.session.commit()
    return prop


@pytest.fixture
def room_type(property_):
    from app.accommodation.models.room import RoomType

    rt = RoomType(
        property_id=property_.id,
        name="Standard",
        description="Standard room",
        max_guests=2,
        bedrooms=1,
        beds=1,
        bathrooms=1.0,
        base_price_per_night=Decimal("100.00"),
        currency="USD",
        cleaning_fee=Decimal("0.00"),
        service_fee_pct=Decimal("10.0"),
        total_units=5,
        is_active=True,
    )
    db.session.add(rt)
    db.session.commit()
    return rt


@pytest.fixture
def booking(event, actor, property_, room_type):
    check_in = datetime.now(timezone.utc).date()
    check_out = check_in + timedelta(days=2)
    num_nights = (check_out - check_in).days

    booking = AccommodationBooking(
        booking_reference=f"BOOK-{uuid.uuid4().hex[:8].upper()}",
        idempotency_key=f"idemp-{uuid.uuid4().hex}",
        event_id=event.id,
        property_id=property_.id,
        room_type_id=room_type.id,
        host_user_id=actor.id,
        guest_user_id=actor.id,
        booked_by_user_id=actor.id,
        check_in=check_in,
        check_out=check_out,
        num_nights=num_nights,
        num_guests=2,
        rooms_requested=1,
        nightly_rate=Decimal("100.00"),
        cleaning_fee=Decimal("0.00"),
        service_fee=Decimal("0.00"),
        taxes=Decimal("0.00"),
        total_amount=Decimal("200.00"),
        currency="USD",
        payment_status="pending",
        status="confirmed",
        context_type="event",
        context_id=str(event.id),
        booking_type="self",
        payment_timing="pay_now",
        payment_guaranteed=True,
        guarantee_type="payment_confirmed",
    )
    booking.calculate_totals()
    db.session.add(booking)
    db.session.commit()
    return booking


@pytest.fixture
def second_booking(event, actor, room_type):
    check_in = datetime.now(timezone.utc).date()
    check_out = check_in + timedelta(days=3)
    num_nights = (check_out - check_in).days

    booking = AccommodationBooking(
        booking_reference=f"BOOK-{uuid.uuid4().hex[:8].upper()}",
        idempotency_key=f"idemp-{uuid.uuid4().hex}",
        event_id=event.id,
        property_id=room_type.property_id,
        room_type_id=room_type.id,
        host_user_id=actor.id,
        guest_user_id=actor.id,
        booked_by_user_id=actor.id,
        check_in=check_in,
        check_out=check_out,
        num_nights=num_nights,
        num_guests=2,
        rooms_requested=1,
        nightly_rate=Decimal("150.00"),
        cleaning_fee=Decimal("0.00"),
        service_fee=Decimal("0.00"),
        taxes=Decimal("0.00"),
        total_amount=Decimal("300.00"),
        currency="USD",
        payment_status="pending",
        status="confirmed",
        context_type="event",
        context_id=str(event.id),
        booking_type="self",
        payment_timing="pay_now",
        payment_guaranteed=True,
        guarantee_type="payment_confirmed",
    )
    booking.calculate_totals()
    db.session.add(booking)
    db.session.commit()
    return booking


# Ownership-boundary tests ------------------------------------------------------

def test_assignment_does_not_mutate_booking_capacity(event, actor, registration, booking, monkeypatch):
    """Assignment must not widen booking capacity or mutate the booking row.

    Events coordinates a slot into the existing booking; capacity is owned by
    Accommodation and must remain untouched by the Events side.
    """
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    num_guests_before = booking.num_guests
    status_before = booking.status

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    db.session.refresh(booking)
    assert booking.num_guests == num_guests_before
    assert booking.status == status_before

    # X-axis: the accommodation-owned count drove the decision, not the booking row.
    from app.accommodation.models.guest_registration import GuestRegistration
    active = GuestRegistration.query.filter_by(
        booking_id=booking.id, is_active=True
    ).count()
    assert active == 1
    assert assignment.accommodation_booking_id == booking.id


def test_assignment_creates_no_new_booking(event, actor, registration, booking, monkeypatch):
    """Assignment must not create an AccommodationBooking.

    EventAssignment is a coordination record only; the accommodation booking is
    created and owned by the accommodation module.
    """
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    count_before = AccommodationBooking.query.filter_by(
        event_id=event.id, is_deleted=False
    ).count()

    GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )

    count_after = AccommodationBooking.query.filter_by(
        event_id=event.id, is_deleted=False
    ).count()
    assert count_after == count_before


def test_event_assignment_is_coordination_ref_not_ownership_fk():
    """event_assignments.accommodation_booking_id must carry NO FK to accommodation.

    It is a CROSS_MODULE_REF coordination pointer; ownership lives in the
    accommodation module. An FK here would make Event own the accommodation row.
    """
    from app.utils.id_kinds import IDKind
    from app.events.models import EventAssignment

    col = EventAssignment.__table__.columns["accommodation_booking_id"]
    assert len(col.foreign_keys) == 0
    assert col.info.get("id_kind") == IDKind.CROSS_MODULE_REF


def test_booking_of_another_event_or_owner_rejected(event, actor, other_actor, registration, property_, room_type, monkeypatch):
    """A booking owned by someone else / reserved for another event must be rejected."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    from app.events.models import Event

    other_event = Event(
        public_id=str(uuid.uuid4()),
        event_ref=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        slug=f"other-event-{uuid.uuid4().hex[:8]}",
        name="Other Event",
        organizer_id=other_actor.id,
        city="Other City",
        country="UG",
        description="Other event",
        category="general",
        max_capacity=100,
        registration_fee=Decimal("0.00"),
        currency="USD",
        start_date=datetime.now(timezone.utc).date(),
        end_date=datetime.now(timezone.utc).date() + timedelta(days=2),
        status="pending_approval",
    )
    db.session.add(other_event)
    db.session.commit()

    check_in = datetime.now(timezone.utc).date()
    check_out = check_in + timedelta(days=2)
    foreign_booking = AccommodationBooking(
        booking_reference=f"BOOK-{uuid.uuid4().hex[:8].upper()}",
        idempotency_key=f"idemp-{uuid.uuid4().hex}",
        event_id=other_event.id,
        property_id=property_.id,
        room_type_id=room_type.id,
        host_user_id=other_actor.id,
        guest_user_id=other_actor.id,
        booked_by_user_id=other_actor.id,
        check_in=check_in,
        check_out=check_out,
        num_nights=(check_out - check_in).days,
        num_guests=2,
        rooms_requested=1,
        nightly_rate=Decimal("100.00"),
        cleaning_fee=Decimal("0.00"),
        service_fee=Decimal("0.00"),
        taxes=Decimal("0.00"),
        total_amount=Decimal("200.00"),
        currency="USD",
        payment_status="pending",
        status="confirmed",
        context_type="event",
        context_id=str(other_event.id),
        booking_type="self",
        payment_timing="pay_now",
        payment_guaranteed=True,
        guarantee_type="payment_confirmed",
    )
    db.session.add(foreign_booking)
    db.session.commit()

    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, foreign_booking.booking_reference
        )
    assert exc.value.code == "BOOKING_EVENT_MISMATCH"


def test_cancellation_routes_slot_release_through_contract(event, actor, registration, booking, monkeypatch):
    """Cancellation must release the guest slot via the accommodation contract only."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )

    calls = []

    original = AccommodationCoordinationContract.release_event_guest_slot

    def wrapped_release(booking_reference, **kwargs):
        calls.append((booking_reference,))
        return original(booking_reference, **kwargs)

    monkeypatch.setattr(
        AccommodationCoordinationContract, "release_event_guest_slot", wrapped_release
    )

    cancelled = GuestCoordinationService.cancel(event, actor, registration.registration_ref, "accommodation")

    assert calls, "Events must release the slot through the accommodation contract"
    assert calls[0][0] == booking.booking_reference
    assert cancelled.accommodation_booking_id is None
    from app.accommodation.models.guest_registration import GuestRegistration
    active = GuestRegistration.query.filter_by(
        booking_id=booking.id, event_assignment_id=assignment.id, is_active=True
    ).count()
    assert active == 0


def test_events_module_has_no_direct_guest_registration_write():
    """Regression guard: the Events module must not import or write GuestRegistration directly."""
    from pathlib import Path
    import app.events.guest_coordination_service as svc

    source = Path(svc.__file__).read_text(encoding="utf-8")
    # The word may appear in ownership comments; what must never appear is a
    # direct write path: importing the model, calling slot.remove by hand, or
    # importing the guest_registration module.
    assert "from app.accommodation.models.guest_registration import GuestRegistration" not in source
    assert "GuestRegistration(" not in source
    assert "slot.remove(" not in source


def test_assignment_creates_no_wallet_account(event, actor, registration, booking, monkeypatch):
    """Assignment must not mint a wallet account for the guest."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    from app.wallet.models.ledger import AccountModel
    count_before = db.session.query(AccountModel).count()

    GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )

    count_after = db.session.query(AccountModel).count()
    assert count_after == count_before


def test_assignment_creates_no_payment_transaction(event, actor, registration, booking, monkeypatch):
    """Assignment must not create a payment transaction."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    from app.wallet.models.transaction import TransactionModel
    count_before = db.session.query(TransactionModel).count()

    GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )

    count_after = db.session.query(TransactionModel).count()
    assert count_after == count_before


def test_assignment_creates_no_ledger_entries(event, actor, registration, booking, monkeypatch):
    """Assignment must not write wallet ledger entries (no financial effect)."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    from app.wallet.models.ledger import LedgerEntryModel
    count_before = db.session.query(LedgerEntryModel).count()

    GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )

    count_after = db.session.query(LedgerEntryModel).count()
    assert count_after == count_before


def test_assignment_preserves_booking_state_machine(event, actor, registration, booking, second_booking, monkeypatch):
    """Full assign -> reassign -> cancel cycle must never move the booking stat us.

    Booking lifecycle (status transitions) is owned by the accommodation state
    machine; Events coordination must leave booking status untouched.
    """
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    state_before = booking.status

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    reassigned = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, second_booking.booking_reference
    )
    GuestCoordinationService.cancel(event, actor, registration.registration_ref, "accommodation")

    db.session.refresh(booking)
    db.session.refresh(second_booking)
    assert booking.status == state_before
    assert second_booking.status == state_before