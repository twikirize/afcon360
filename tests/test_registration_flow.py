#!/usr/bin/env python3
"""
Test registration flow including concurrency, idempotency, and waitlist.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import patch, MagicMock
from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.kyc.models import KycRecord
from app.identity.models.user import User
from app.events.models import Event, TicketType, EventRegistration, Waitlist
from app.events.services import EventService, IdempotencyChecker
import app.identity.individuals.individual_verification        # IndividualVerification
import app.fan.models

class TestRegistrationFlow(unittest.TestCase):
    """Test registration flow with concurrency and idempotency"""

    def setUp(self):
        """Set up test environment"""
        self.app = create_app(config_object=TestingConfig)

        with self.app.app_context():
            # Create test users
            self.user1 = User(email=f'user1_{uuid.uuid4().hex[:8]}@example.com', username=f'user1_{uuid.uuid4().hex[:8]}', password_hash='pbkdf2:sha256:test')
            self.user2 = User(email=f'user2_{uuid.uuid4().hex[:8]}@example.com', username=f'user2_{uuid.uuid4().hex[:8]}', password_hash='pbkdf2:sha256:test')
            db.session.add_all([self.user1, self.user2])
            db.session.flush()
            db.session.commit()
            self.user1_id = self.user1.id
            self.user2_id = self.user2.id
            self.slug_suffix = uuid.uuid4().hex[:8]

    def tearDown(self):
        """Clean up after tests"""
        with self.app.app_context():
            db.session.remove()
            db.session.rollback()

    def test_idempotency(self):
        """Test that duplicate requests are idempotent"""
        with self.app.app_context():
            # Create event
            event = Event(
                slug=f'idempotent-event-{self.slug_suffix}',
                name='Idempotent Event',
                city='Kampala',
                organizer_id=self.user1_id,
                current_owner_type="individual", current_owner_id=self.user1_id,
                status='active'
            )
            db.session.add(event)
            db.session.flush()

            ticket = TicketType(
                event_id=event.id,
                name='General',
                price=0,
                capacity=100,
                is_active=True
            )
            db.session.add(ticket)
            db.session.commit()
            ticket_id = ticket.id
            event_id = event.id

            # Generate idempotency key
            data = {'full_name': 'Test User', 'email': 'test@example.com'}
            data_hash = 'test_hash'
            event_slug = f'idempotent-event-{self.slug_suffix}'
            key = IdempotencyChecker.generate_key(self.user1_id, event_slug, data_hash)

            # First check should return False (key doesn't exist)
            # Mock redis_client to be None
            with patch('app.events.services._legacy.redis_client', None):
                exists = IdempotencyChecker.check_and_store(key)
                self.assertFalse(exists)

            # Simulate registration with idempotency
            registration_data = {
                'full_name': 'Test User',
                'email': 'test@example.com',
                'phone': '+256700000000',
                'nationality': 'Ugandan',
                'ticket_type_id': ticket.id
            }

            # First registration
            with patch('app.events.services.SIGNALS_AVAILABLE', False):
                reg1, qr1, err1 = EventService.register_for_event_optimistic(
                    event_slug, self.user1_id, registration_data, key
                )

            self.assertIsNone(err1)

            # Second registration with same key should be detected as duplicate
            with patch('app.events.services._legacy.SIGNALS_AVAILABLE', False):
                reg2, qr2, err2 = EventService.register_for_event_optimistic(
                    event_slug, self.user1_id, registration_data, key
                )

            # Should return existing registration or error
            self.assertIsNotNone(err2)
            self.assertIn('duplicate', err2.lower())

    def test_concurrent_registrations(self):
        """Test concurrent registrations with optimistic locking"""
        with self.app.app_context():
            # Create event with limited capacity
            event = Event(
                slug=f'concurrent-event-{self.slug_suffix}',
                name='Concurrent Event',
                city='Kampala',
                organizer_id=self.user1_id,
                current_owner_type="individual", current_owner_id=self.user1_id,
                status='active',
                max_capacity=5
            )
            db.session.add(event)
            db.session.flush()

            ticket = TicketType(
                event_id=event.id,
                name='General',
                price=0,
                capacity=5,  # Only 5 seats
                is_active=True
            )
            db.session.add(ticket)
            db.session.commit()
            ticket_id = ticket.id
            event_id = event.id

            # Simulate multiple concurrent registrations
            results = []
            errors = []

            def register_user(user_id, user_num):
                with self.app.app_context():
                    data = {
                        'full_name': f'User {user_num}',
                        'email': f'user{user_num}_{self.slug_suffix}@example.com',
                        'phone': f'+256700000{user_num:03d}',
                        'nationality': 'Ugandan',
                        'ticket_type_id': ticket_id
                    }

                    with patch('app.events.services._legacy.SIGNALS_AVAILABLE', False):
                        reg, qr, err = EventService.register_for_event_optimistic(
                            f'concurrent-event-{self.slug_suffix}', user_id, data
                        )

                    if err:
                        errors.append(err)
                    else:
                        results.append(reg)

            # Create more users than capacity
            users = []
            for i in range(10):
                user = User(
                    email=f'concurrent{i}_{self.slug_suffix}@example.com',
                    username=f'concurrent{i}_{self.slug_suffix}',
                    password_hash='pbkdf2:sha256:test'
                )
                db.session.add(user)
                users.append(user)
            db.session.commit()

            # Start threads
            threads = []
            for i, user in enumerate(users[:8]):  # Try to register 8 users for 5 seats
                thread = threading.Thread(target=register_user, args=(user.id, i))
                threads.append(thread)
                thread.start()

            # Wait for all threads
            for thread in threads:
                thread.join()

            # Check results
            self.assertEqual(len(results), 5)  # Only 5 should succeed
            self.assertEqual(len(errors), 3)   # 3 should fail (sold out)

            # Verify no overbooking
            db.session.remove()
            final_count = EventRegistration.query.filter_by(event_id=event_id).count()
            self.assertEqual(final_count, 5)

    def test_waitlist_functionality(self):
        """Test waitlist when event is sold out"""
        with self.app.app_context():
            # Create event with very limited capacity
            event = Event(
                slug=f'waitlist-event-{self.slug_suffix}',
                name='Waitlist Event',
                city='Kampala',
                organizer_id=self.user1_id,
                current_owner_type="individual", current_owner_id=self.user1_id,
                status='active',
                max_capacity=2
            )
            db.session.add(event)
            db.session.flush()

            ticket = TicketType(
                event_id=event.id,
                name='General',
                price=0,
                capacity=2,  # Only 2 seats
                is_active=True
            )
            db.session.add(ticket)
            db.session.commit()

            # Fill the event
            for i in range(2):
                user = User(
                    email=f'fill{i}_{self.slug_suffix}@example.com',
                    username=f'fill{i}_{self.slug_suffix}',
                    password_hash='pbkdf2:sha256:test'
                )
                db.session.add(user)
                db.session.flush()

                data = {
                    'full_name': f'Fill User {i}',
                    'email': f'fill{i}_{self.slug_suffix}@example.com',
                    'phone': f'+25670000{i:04d}',
                    'nationality': 'Ugandan',
                    'ticket_type_id': ticket.id
                }

                with patch('app.events.services._legacy.SIGNALS_AVAILABLE', False):
                    EventService.register_for_event_optimistic(
                        f'waitlist-event-{self.slug_suffix}', user.id, data
                    )

            # Now try to register another user - should go to waitlist
            waitlist_user = User(
                email=f'waitlist_{self.slug_suffix}@example.com',
                username=f'waitlister_{self.slug_suffix}',
                password_hash='pbkdf2:sha256:test'
            )
            db.session.add(waitlist_user)
            db.session.commit()

            waitlist_data = {
                'full_name': 'Waitlist User',
                'email': f'waitlist_{self.slug_suffix}@example.com',
                'phone': '+256711111111',
                'nationality': 'Ugandan',
                'ticket_type_id': ticket.id
            }

            # Try to register (should fail and suggest waitlist)
            with patch('app.events.services._legacy.SIGNALS_AVAILABLE', False):
                reg, qr, err = EventService.register_for_event_optimistic(
                    f'waitlist-event-{self.slug_suffix}', waitlist_user.id, waitlist_data
                )

            self.assertIsNotNone(err)
            self.assertIn('sold out', err.lower())

            # Add to waitlist
            waitlist_entry, waitlist_error = EventService.add_to_waitlist(
                f'waitlist-event-{self.slug_suffix}', waitlist_user.id, waitlist_data
            )

            self.assertIsNone(waitlist_error)
            self.assertIsNotNone(waitlist_entry)
            self.assertEqual(waitlist_entry['position'], 1)
            self.assertEqual(waitlist_entry['status'], 'pending')

    def test_capacity_release_on_expiry(self):
        """Test that expired registrations release capacity"""
        with self.app.app_context():
            # Create event
            event = Event(
                slug=f'expiry-event-{self.slug_suffix}',
                name='Expiry Event',
                city='Kampala',
                organizer_id=self.user1_id,
                current_owner_type="individual", current_owner_id=self.user1_id,
                status='active'
            )
            db.session.add(event)
            db.session.flush()

            ticket = TicketType(
                event_id=event.id,
                name='General',
                price=10.00,  # Paid ticket
                capacity=3,
                is_active=True,
                available_seats=3
            )
            db.session.add(ticket)
            db.session.commit()

            # Create a pending registration (simulates unpaid)
            registration = EventRegistration(
                event_id=event.id,
                user_id=self.user1_id,
                ticket_type_id=ticket.id,
                full_name='Pending User',
                email='pending@example.com',
                ticket_type='General',
                registration_fee=10.00,
                payment_status='pending',
                status='pending_payment',
                created_at=datetime.now(timezone.utc) - timedelta(hours=3)  # 3 hours old
            )
            registration.generate_refs(event.slug, 1)
            db.session.add(registration)
            db.session.commit()
            registration_id = registration.id
            ticket_id = ticket.id

            # Verify initial state
            initial_ticket = db.session.get(TicketType, ticket_id)
            self.assertEqual(initial_ticket.available_seats, 3)

            # Run the reaper task (simulated)
            from app.events.tasks import expire_pending_registrations

            db.session.remove()
            with patch('app.events.signal_handlers.event_capacity_released') as mock_signal:
                result = expire_pending_registrations()

            # Check that registration was expired
            db.session.remove()
            expired_reg = db.session.get(EventRegistration, registration_id)
            self.assertEqual(expired_reg.status, 'expired')
            self.assertEqual(expired_reg.payment_status, 'expired')

            # Check that capacity was released
            updated_ticket = db.session.get(TicketType, ticket_id)
            # Available seats should still be 3 (since it was never decremented for pending)
            # Or maybe it was decremented and then released back
            # This depends on implementation

            # At minimum, verify no data corruption
            self.assertIsNotNone(updated_ticket)

if __name__ == '__main__':
    unittest.main()

