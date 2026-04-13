#!/usr/bin/env python3
"""
Test payment flow integration with wallet service.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from flask import Flask
from app.extensions import db
from app.events.models import Event, TicketType, EventRegistration
from app.events.services import EventService
from app.identity.models.user import User
import app.kyc.models                                          # KycRecord
import app.identity.individuals.individual_verification        # IndividualVerification
import app.fan.models

class TestPaymentFlow(unittest.TestCase):
    """Test payment integration with wallet"""

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
            db.create_all()

            # Create test user
            self.test_user = User(
                user_id='payment_user',
                email='payment@example.com',
                username='paymentuser'
            )
            db.session.add(self.test_user)
            db.session.commit()

    def tearDown(self):
        """Clean up after tests"""
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_free_registration_no_payment(self):
        """Test free registration doesn't require payment"""
        with self.app.app_context():
            # Create free event
            event = Event(
                slug='free-event',
                name='Free Event',
                city='Kampala',
                organizer_id=self.test_user.id,
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

            with patch('app.events.services.SIGNALS_AVAILABLE', False):
                registration, qr_code, error = EventService.register_for_event_with_payment(
                    'free-event', self.test_user.id, registration_data
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
                slug='paid-event',
                name='Paid Event',
                city='Kampala',
                organizer_id=self.test_user.id,
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
            mock_wallet_service.debit.return_value = (
                True,
                {'transaction_id': 'wallet_txn_12345'},
                None
            )

            registration_data = {
                'full_name': 'Paying User',
                'email': 'paying@example.com',
                'phone': '+256711111111',
                'nationality': 'Ugandan',
                'ticket_type_id': ticket.id
            }

            with patch('app.events.services.WalletService', return_value=mock_wallet_service):
                with patch('app.events.services.SIGNALS_AVAILABLE', False):
                    registration, qr_code, error = EventService.register_for_event_with_payment(
                        'paid-event', self.test_user.id, registration_data
                    )

            # Verify wallet was called correctly
            mock_wallet_service.debit.assert_called_once()
            call_args = mock_wallet_service.debit.call_args

            self.assertEqual(call_args[1]['user_id'], self.test_user.id)
            self.assertEqual(call_args[1]['amount'], Decimal('50.00'))
            self.assertEqual(call_args[1]['currency'], 'USD')
            self.assertIn('EVT-REG-paid-event', call_args[1]['reference'])

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
                slug='expensive-event',
                name='Expensive Event',
                city='Kampala',
                organizer_id=self.test_user.id,
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
            mock_wallet_service.debit.return_value = (
                False,
                None,
                'Insufficient balance. Available: 100.00 USD, Required: 1000.00 USD'
            )

            registration_data = {
                'full_name': 'Broke User',
                'email': 'broke@example.com',
                'phone': '+256722222222',
                'nationality': 'Ugandan',
                'ticket_type_id': ticket.id
            }

            with patch('app.events.services.WalletService', return_value=mock_wallet_service):
                with patch('app.events.services.SIGNALS_AVAILABLE', False):
                    registration, qr_code, error = EventService.register_for_event_with_payment(
                        'expensive-event', self.test_user.id, registration_data
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
                slug='wallet-down-event',
                name='Wallet Down Event',
                city='Kampala',
                organizer_id=self.test_user.id,
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
                        'wallet-down-event', self.test_user.id, registration_data
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
