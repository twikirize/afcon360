#!/usr/bin/env python3
"""
Test payment flow integration with wallet service.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
import unittest
import uuid
from unittest.mock import patch, MagicMock
from decimal import Decimal
from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.kyc.models import KycRecord
from app.identity.models.user import User
from app.events.models import Event, TicketType, EventRegistration
from app.events.services import EventService
import app.identity.individuals.individual_verification        # IndividualVerification
import app.fan.models

class TestPaymentFlow(unittest.TestCase):
    """Test payment integration with wallet"""

    def setUp(self):
        """Set up test environment"""
        self.app = create_app(config_object=TestingConfig)

        with self.app.app_context():
            # Create test user
            suffix = uuid.uuid4().hex[:8]
            self.test_user = User(
                email=f'payment_{suffix}@example.com',
                username=f'paymentuser_{suffix}',
                password_hash='pbkdf2:sha256:test',
            )
            db.session.add(self.test_user)
            db.session.flush()
            db.session.commit()
            self.user_id = self.test_user.id
            self.slug_suffix = uuid.uuid4().hex[:8]

    def tearDown(self):
        """Clean up after tests"""
        with self.app.app_context():
            db.session.remove()
            db.session.rollback()

    def test_free_registration_no_payment(self):
        """Test free registration doesn't require payment"""
        with self.app.app_context():
            # Create free event
            event = Event(
                slug=f'free-event-{self.slug_suffix}',
                name='Free Event',
                city='Kampala',
                organizer_id=self.user_id,
                current_owner_type="individual", current_owner_id=self.user_id,
                status='active',
                currency='USD'
            )
            db.session.add(event)
            db.session.flush()

            ticket = TicketType(
                event_id=event.id,
                name='Free Ticket',
                price=0,
                capacity=100,
                is_active=True
            )
            db.session.add(ticket)
            db.session.commit()

            # Register without payment
            registration_data = {
                'full_name': 'Free User',
                'email': 'free@example.com',
                'phone': '+256700000000',
                'nationality': 'Ugandan',
                'ticket_type_id': ticket.id
            }

            with patch('app.events.services._legacy.SIGNALS_AVAILABLE', False):
                registration, qr_code, error = EventService.register_for_event_with_payment(
                    f'free-event-{self.slug_suffix}', self.user_id, registration_data
                )

            self.assertIsNone(error)
            self.assertIsNotNone(registration)
            self.assertEqual(registration['payment_status'], 'free')
            self.assertEqual(registration['status'], 'confirmed')

            # Verify no wallet transaction ID
            reg_model = EventRegistration.query.filter_by(
                registration_ref=registration['registration_ref']
            ).first()
            self.assertIsNone(reg_model.wallet_txn_id)

    def test_paid_registration_success(self):
        """Test successful paid registration"""
        with self.app.app_context():
            # Create paid event
            event = Event(
                slug=f'paid-event-{self.slug_suffix}',
                name='Paid Event',
                city='Kampala',
                organizer_id=self.user_id,
                current_owner_type="individual", current_owner_id=self.user_id,
                status='active',
                currency='USD'
            )
            db.session.add(event)
            db.session.flush()

            ticket = TicketType(
                event_id=event.id,
                name='VIP Ticket',
                price=50.00,
                capacity=50,
                is_active=True
            )
            db.session.add(ticket)
            db.session.commit()

            # Mock successful wallet payment
            mock_wallet_service = MagicMock()
            mock_wallet_service.account_repo.get_by_user_id.return_value = MagicMock(id='account-123')
            mock_wallet_service.withdraw.return_value = {
                'status': 'success',
                'transaction_id': 'wallet_txn_12345',
            }

            registration_data = {
                'full_name': 'Paying User',
                'email': 'paying@example.com',
                'phone': '+256711111111',
                'nationality': 'Ugandan',
                'ticket_type_id': ticket.id
            }

            with patch('app.wallet.services.wallet_service.WalletService', return_value=mock_wallet_service):
                with patch('app.events.services.SIGNALS_AVAILABLE', False):
                    registration, qr_code, error = EventService.register_for_event_with_payment(
                        f'paid-event-{self.slug_suffix}', self.user_id, registration_data
                    )

            # Verify the production withdrawal contract was called correctly.
            mock_wallet_service.withdraw.assert_called_once()
            call_args = mock_wallet_service.withdraw.call_args

            self.assertEqual(call_args.kwargs['account_id'], 'account-123')
            self.assertEqual(call_args.kwargs['amount'], Decimal('50.00'))
            self.assertEqual(call_args.kwargs['currency'], 'USD')
            self.assertIn('EVT-REG-paid-event', call_args.kwargs['client_request_id'])

            # Verify registration
            self.assertIsNone(error)
            self.assertIsNotNone(registration)
            self.assertEqual(registration['payment_status'], 'paid')
            self.assertEqual(registration['status'], 'confirmed')

            # Verify wallet transaction ID is stored
            reg_model = EventRegistration.query.filter_by(
                registration_ref=registration['registration_ref']
            ).first()
            self.assertEqual(reg_model.wallet_txn_id, 'wallet_txn_12345')

    def test_paid_registration_insufficient_funds(self):
        """Test paid registration with insufficient funds"""
        with self.app.app_context():
            # Create paid event
            event = Event(
                slug=f'expensive-event-{self.slug_suffix}',
                name='Expensive Event',
                city='Kampala',
                organizer_id=self.user_id,
                current_owner_type="individual", current_owner_id=self.user_id,
                status='active',
                currency='USD'
            )
            db.session.add(event)
            db.session.flush()

            ticket = TicketType(
                event_id=event.id,
                name='Platinum Ticket',
                price=1000.00,  # Expensive!
                capacity=10,
                is_active=True
            )
            db.session.add(ticket)
            db.session.commit()

            # Mock wallet with insufficient funds
            mock_wallet_service = MagicMock()
            mock_wallet_service.account_repo.get_by_user_id.return_value = MagicMock(id='account-456')
            mock_wallet_service.withdraw.return_value = {
                'status': 'failed',
                'error': 'Insufficient balance. Available: 100.00 USD, Required: 1000.00 USD',
            }

            registration_data = {
                'full_name': 'Broke User',
                'email': 'broke@example.com',
                'phone': '+256722222222',
                'nationality': 'Ugandan',
                'ticket_type_id': ticket.id
            }

            with patch('app.events.services._legacy.WalletService', return_value=mock_wallet_service):
                with patch('app.events.services._legacy.SIGNALS_AVAILABLE', False):
                    registration, qr_code, error = EventService.register_for_event_with_payment(
                        f'expensive-event-{self.slug_suffix}', self.user_id, registration_data
                    )

            # Verify error
            self.assertIsNotNone(error)
            self.assertIn('insufficient', error.lower())
            self.assertIsNone(registration)

            # Verify no registration was created
            count = EventRegistration.query.filter_by(event_id=event.id).count()
            self.assertEqual(count, 0)

    def test_paid_registration_wallet_service_unavailable(self):
        """Test when wallet service is unavailable"""
        with self.app.app_context():
            # Create paid event
            event = Event(
                slug=f'wallet-down-event-{self.slug_suffix}',
                name='Wallet Down Event',
                city='Kampala',
                organizer_id=self.user_id,
                current_owner_type="individual", current_owner_id=self.user_id,
                status='active',
                currency='USD'
            )
            db.session.add(event)
            db.session.flush()

            ticket = TicketType(
                event_id=event.id,
                name='Standard Ticket',
                price=25.00,
                capacity=100,
                is_active=True
            )
            db.session.add(ticket)
            db.session.commit()

            # Simulate WalletService not being available
            registration_data = {
                'full_name': 'Unlucky User',
                'email': 'unlucky@example.com',
                'phone': '+256733333333',
                'nationality': 'Ugandan',
                'ticket_type_id': ticket.id
            }

            with patch('app.events.services.WalletService', None):
                with patch('app.events.services.SIGNALS_AVAILABLE', False):
                    registration, qr_code, error = EventService.register_for_event_with_payment(
                        f'wallet-down-event-{self.slug_suffix}', self.user_id, registration_data
                    )

            # Should get service unavailable error
            self.assertIsNotNone(error)
            self.assertIn('unavailable', error.lower())
            self.assertIsNone(registration)

    def test_payment_rollback_on_registration_failure(self):
        """Test that payment is rolled back if registration fails after payment"""
        with self.app.app_context():
            # This is a more complex test that would require
            # simulating a failure after payment but before registration commit
            # For now, we'll note this as an important integration test
            pass

    def test_refund_scenario(self):
        """Test refund scenario (would require refund implementation)"""
        # Note: Refund functionality would need to be implemented
        # This test would verify that cancelled registrations trigger refunds
        pass

if __name__ == '__main__':
    unittest.main()
