"""
PostgreSQL regression tests: account-optional guest coordination.

These prove that:
  * a guest without an AFCON360 account can be assigned accommodation/transport
  * the assignment is linked by ``registration_id`` and ``attendee_id`` is NULL
  * a guest with an existing account still works
  * no user account is auto-created by assignment / third-party registration

Per the AFCON360 testing contract these run against a PostgreSQL test database
(``TEST_DATABASE_URL``).  They require the schema to be migrated (including the
``event_guests`` table and ``event_assignments.guest_id`` column which are
referenced by the models).
"""
import sys
import os
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.identity.models.user import User
from app.events.models import (
    Event,
    TicketType,
    EventRegistration,
    EventAssignment,
)
from app.events.services import EventService
from app.events.attendee_accounts import (
    find_or_create_attendee_user,
    find_attendee_user_id,
    create_attendee_user,
)
from app.events.guest_coordination_service import GuestCoordinationService
from app.events.constants import BookingType


class TestAccountOptionalAttendeeResolution(unittest.TestCase):
    """Resolver behaviour — does not need event_assignments rows loaded."""

    def setUp(self):
        self.app = create_app(config_object=TestingConfig)
        with self.app.app_context():
            suffix = uuid.uuid4().hex[:8]
            self.existing = User(
                email=f"known_{suffix}@example.com",
                username=f"knownuser_{suffix}",
                password_hash="pbkdf2:sha256:test",
            )
            db.session.add(self.existing)
            db.session.commit()
            self.existing_id = self.existing.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.session.rollback()

    def test_existing_account_resolves_without_creating(self):
        with self.app.app_context():
            before = User.query.count()
            user_id, error = find_or_create_attendee_user(
                email=self.existing.email, name="Known User", create_guest_account=False
            )
            self.assertIsNone(error)
            self.assertEqual(user_id, self.existing_id)
            self.assertEqual(User.query.count(), before)

    def test_unknown_account_is_optional_by_default(self):
        with self.app.app_context():
            before = User.query.count()
            user_id, error = find_or_create_attendee_user(
                email=f"stranger_{uuid.uuid4().hex[:8]}@example.com",
                name="Stranger",
                create_guest_account=False,
            )
            self.assertIsNone(user_id)
            self.assertIsNone(error)
            self.assertEqual(User.query.count(), before)

    def test_create_guest_account_explicitly_creates(self):
        with self.app.app_context():
            email = f"newguest_{uuid.uuid4().hex[:8]}@example.com"
            user_id, error = find_or_create_attendee_user(
                email=email, name="New Guest", create_guest_account=True
            )
            self.assertIsNone(error)
            self.assertIsNotNone(user_id)
            self.assertIsNotNone(User.query.filter_by(email=email).first())

    def test_find_attendee_user_id_helper(self):
        with self.app.app_context():
            user_id, error = find_attendee_user_id(self.existing.email)
            self.assertEqual(user_id, self.existing_id)
            self.assertIsNone(error)
            missing_id, missing_err = find_attendee_user_id(
                f"nope_{uuid.uuid4().hex[:8]}@example.com"
            )
            self.assertIsNone(missing_id)
            self.assertIsNone(missing_err)


class TestAccountOptionalAssignment(unittest.TestCase):
    """Assignment behaviour against a migrated PostgreSQL schema."""

    def setUp(self):
        self.app = create_app(config_object=TestingConfig)
        with self.app.app_context():
            suffix = uuid.uuid4().hex[:8]
            self.host = User(
                email=f"host_{suffix}@example.com",
                username=f"hostuser_{suffix}",
                password_hash="pbkdf2:sha256:test",
            )
            db.session.add(self.host)
            db.session.commit()
            self.host_id = self.host.id

            self.event = Event(
                slug=f"opt-event-{suffix}",
                name="Optional Account Event",
                city="Kampala",
                organizer_id=self.host_id,
                current_owner_type="individual",
                current_owner_id=self.host_id,
                status="active",
                currency="USD",
            )
            db.session.add(self.event)
            db.session.flush()
            self.ticket = TicketType(
                event_id=self.event.id,
                name="General",
                price=0,
                capacity=100,
                is_active=True,
            )
            db.session.add(self.ticket)
            db.session.commit()
            self.event_id = self.event.id
            self.event_slug = self.event.slug
            self.ticket_id = self.ticket.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.session.rollback()

    def _make_registration(self, user_id=None, attendee_user_id=None, email=None):
        # Assumes caller is already in an app context
        suffix = uuid.uuid4().hex[:8]
        reg = EventRegistration(
            event_id=self.event_id,
            ticket_type_id=self.ticket_id,
            user_id=user_id,
            attendee_user_id=attendee_user_id,
            full_name=f"Guest {suffix}",
            email=email or f"guest_{suffix}@example.com",
            ticket_type="General",
            registration_fee=0,
            payment_status="free",
            status="confirmed",
            booked_by_user_id=self.host_id,
            booking_type=BookingType.THIRD_PARTY.value,
        )
        # Generate refs BEFORE flush to satisfy NOT NULL constraints
        # Use sequence=1 since each test gets a fresh event (no existing registrations)
        reg.generate_refs(self.event_slug, 1)
        db.session.add(reg)
        db.session.flush()
        db.session.commit()
        return reg.id

    def test_guest_without_account_assigned_by_registration(self):
        with self.app.app_context():
            reg_id = self._make_registration(user_id=None, attendee_user_id=None)
            reg = db.session.get(EventRegistration, reg_id)
            assignment = GuestCoordinationService._assignment(self.event, reg)
            db.session.commit()

            self.assertIsNone(assignment.attendee_id)
            self.assertEqual(assignment.registration_id, reg_id)
            self.assertEqual(assignment.event_id, self.event_id)
            # No user account was created for the guest.
            self.assertIsNone(User.query.filter_by(email=reg.email).first())

    def test_guest_with_existing_account_links_attendee_id(self):
        with self.app.app_context():
            suffix = uuid.uuid4().hex[:8]
            account = User(
                email=f"acct_{suffix}@example.com",
                username=f"acctuser_{suffix}",
                password_hash="pbkdf2:sha256:test",
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            reg_id = self._make_registration(
                user_id=account_id, attendee_user_id=account_id,
                email=account.email,
            )
            reg = db.session.get(EventRegistration, reg_id)
            assignment = GuestCoordinationService._assignment(self.event, reg)
            db.session.commit()

            self.assertEqual(assignment.attendee_id, account_id)
            self.assertEqual(assignment.registration_id, reg_id)

    def test_repeated_assignment_reuses_same_row(self):
        with self.app.app_context():
            reg_id = self._make_registration(user_id=None, attendee_user_id=None)
            reg = db.session.get(EventRegistration, reg_id)
            first = GuestCoordinationService._assignment(self.event, reg)
            db.session.commit()
            second = GuestCoordinationService._assignment(self.event, reg)
            db.session.commit()
            self.assertEqual(first.id, second.id)
            self.assertEqual(
                EventAssignment.query.filter_by(event_id=self.event_id).count(), 1
            )

    def test_third_party_registration_does_not_create_account(self):
        with self.app.app_context():
            # Avoid signal/notification machinery for the test
            import app.events.services as svc
            svc.SIGNALS_AVAILABLE = False

            suffix = uuid.uuid4().hex[:8]
            email = f"thirdparty_{suffix}@example.com"
            before = User.query.count()
            registration, qr_code, error = EventService.register_for_event(
                self.event.slug,
                self.host_id,
                {
                    "full_name": f"Third Party {suffix}",
                    "email": email,
                    "phone": "+256700000000",
                    "ticket_type_id": self.ticket_id,
                },
                booking_type=BookingType.THIRD_PARTY.value,
                attendee_email=email,
                attendee_name=f"Third Party {suffix}",
                attendee_phone="+256700000000",
            )
            self.assertIsNone(error)
            self.assertIsNotNone(registration)

            reg_model = db.session.get(EventRegistration, registration["id"])
            self.assertIsNotNone(reg_model)
            # For third-party bookings, user_id and attendee_user_id are set to the booker's ID
            # (per model design: "Currently always equals user_id for third_party/group bookings")
            self.assertEqual(reg_model.user_id, self.host_id)
            self.assertEqual(reg_model.attendee_user_id, self.host_id)
            self.assertEqual(reg_model.booking_type, BookingType.THIRD_PARTY.value)
            # Still no account auto-created for the guest.
            self.assertEqual(User.query.count(), before)


if __name__ == "__main__":
    unittest.main()
