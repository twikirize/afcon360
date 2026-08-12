"""
AFCON360 Notification Mock / Development Fixtures

Python port of the legacy TypeScript fixtures that used to live in
``app/src/data/mockData.ts`` and ``app/src/notifications/templateService.ts``.

Two kinds of fixtures are provided:

1. **Domain fixtures** (users, wallets, events, properties, vehicles, KYC).
   These are plain dictionaries only. The real persistent models live in their
   own modules (``app.identity.models.user.User``,
   ``app.wallet.models.transaction.TransactionModel``,
   ``app.accommodation.models.property.Property``, ``app.events.models.Event``,
   ``app.transport.models.Vehicle``, ``app.kyc.models.KycRecord``) and are
   deliberately **not** duplicated here.

2. **Notification fixtures** (templates, preferences, notifications, logs).
   These map onto the real notification SQLAlchemy models and can be persisted
   via :func:`seed_mock_notification_data`.

Usage::

    from app.notifications.mock_data import seed_mock_notification_data

    # Dry run - just get the dicts back, nothing is written.
    fixtures = seed_mock_notification_data()

    # Persist notification templates/preferences/notifications/logs.
    summary = seed_mock_notification_data(db.session, user_id=1)
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

__all__ = [
    'MOCK_USERS',
    'MOCK_WALLETS',
    'MOCK_EVENTS',
    'MOCK_EVENT_REGISTRATIONS',
    'MOCK_PROPERTIES',
    'MOCK_PROPERTY_BOOKINGS',
    'MOCK_VEHICLES',
    'MOCK_TRANSPORT_BOOKINGS',
    'MOCK_KYC_SUBMISSIONS',
    'DEFAULT_NOTIFICATION_TEMPLATES',
    'MOCK_NOTIFICATION_PREFERENCES',
    'MOCK_NOTIFICATIONS',
    'get_mock_data',
    'get_mock_user',
    'get_mock_wallet',
    'render_mock_template',
    'seed_mock_notification_data',
    'clear_mock_notification_data',
]


def _iso(value: str) -> str:
    """Identity helper kept so fixtures read like the original TS source."""
    return value


# ---------------------------------------------------------------------------
# Domain fixtures (ported from src/data/mockData.ts + src/types.ts)
# ---------------------------------------------------------------------------

MOCK_USERS: List[Dict[str, Any]] = [
    {
        'id': 'usr_fan1',
        'public_id': 'pub_usr_fan_001',
        'username': 'afcon_fan_ug',
        'email': 'fan@afcon360.com',
        'role': 'fan',
        'active_role': 'fan',
        'available_roles': ['fan', 'organizer', 'host'],
        'kyc_tier': 2,
        'kyc_status': 'verified',
        'full_name': 'David Mukasa',
        'phone': '+256771234567',
        'national_id': 'CM98012345ABCD',
        'created_at': _iso('2026-01-15T10:00:00Z'),
    },
    {
        'id': 'usr_host1',
        'public_id': 'pub_usr_host_001',
        'username': 'serena_hospitality',
        'email': 'host@afcon360.com',
        'role': 'host',
        'active_role': 'host',
        'available_roles': ['host', 'fan'],
        'kyc_tier': 3,
        'kyc_status': 'verified',
        'full_name': 'Grace Akello',
        'phone': '+256782999888',
        'national_id': 'CF92098765XYZ',
        'created_at': _iso('2026-01-10T09:00:00Z'),
    },
    {
        'id': 'usr_driver1',
        'public_id': 'pub_usr_driver_001',
        'username': 'vip_transporter',
        'email': 'driver@afcon360.com',
        'role': 'driver',
        'active_role': 'driver',
        'available_roles': ['driver', 'fan'],
        'kyc_tier': 3,
        'kyc_status': 'verified',
        'full_name': 'John Kato',
        'phone': '+256701112233',
        'national_id': 'CM90044455QWE',
        'created_at': _iso('2026-02-01T12:00:00Z'),
    },
    {
        'id': 'usr_admin1',
        'public_id': 'pub_usr_admin_001',
        'username': 'afcon_owner_admin',
        'email': 'admin@afcon360.com',
        'role': 'super_admin',
        'active_role': 'super_admin',
        'available_roles': ['super_admin', 'moderator', 'compliance_officer', 'fan'],
        'kyc_tier': 4,
        'kyc_status': 'verified',
        'full_name': 'Super Admin Control',
        'phone': '+256700000000',
        'national_id': None,
        'created_at': _iso('2025-12-01T08:00:00Z'),
    },
]


MOCK_WALLETS: Dict[str, Dict[str, Any]] = {
    'usr_fan1': {
        'user_id': 'usr_fan1',
        'balance_ugx': 1850000,
        'balance_usd': 500.0,
        'escrow_balance_ugx': 350000,
        'transactions': [
            {
                'id': 'tx_001',
                'public_id': 'pub_tx_001',
                'type': 'deposit',
                'amount': 2000000,
                'currency': 'UGX',
                'status': 'completed',
                'reference': 'MTN_MOMO_982341',
                'description': 'MTN Mobile Money Deposit',
                'counterparty': None,
                'created_at': _iso('2026-03-01T14:30:00Z'),
            },
            {
                'id': 'tx_002',
                'public_id': 'pub_tx_002',
                'type': 'payment',
                'amount': 150000,
                'currency': 'UGX',
                'status': 'completed',
                'reference': 'TKT_AFCON_2027_01',
                'description': 'VIP Pass - Uganda vs Kenya Match',
                'counterparty': None,
                'created_at': _iso('2026-03-02T10:15:00Z'),
            },
        ],
    },
    'usr_host1': {
        'user_id': 'usr_host1',
        'balance_ugx': 8400000,
        'balance_usd': 2200.0,
        'escrow_balance_ugx': 1200000,
        'transactions': [
            {
                'id': 'tx_003',
                'public_id': 'pub_tx_003',
                'type': 'payout',
                'amount': 3200000,
                'currency': 'UGX',
                'status': 'completed',
                'reference': 'BANK_SETTLEMENT_441',
                'description': 'Stanbic Bank Accommodation Earnings Payout',
                'counterparty': None,
                'created_at': _iso('2026-02-28T16:00:00Z'),
            },
        ],
    },
    'usr_driver1': {
        'user_id': 'usr_driver1',
        'balance_ugx': 650000,
        'balance_usd': 150.0,
        'escrow_balance_ugx': 0,
        'transactions': [
            {
                'id': 'tx_004',
                'public_id': 'pub_tx_004',
                'type': 'deposit',
                'amount': 300000,
                'currency': 'UGX',
                'status': 'completed',
                'reference': 'AIRTEL_MONEY_5511',
                'description': 'Airtel Money Shuttle Deposit',
                'counterparty': None,
                'created_at': _iso('2026-03-03T08:00:00Z'),
            },
        ],
    },
}


MOCK_EVENTS: List[Dict[str, Any]] = [
    {
        'id': 'evt_001',
        'public_id': 'pub_evt_afcon2027',
        'title': 'AFCON 2027 Opener: Uganda Cranes vs Kenya Harambee Stars',
        'category': 'Sports',
        'location': 'Kampala, Uganda',
        'venue': 'Mandela National Stadium, Namboole',
        'start_date': _iso('2027-06-12T16:00:00Z'),
        'end_date': _iso('2027-06-12T19:00:00Z'),
        'price_ugx': 75000,
        'capacity': 45000,
        'registered_count': 31200,
        'image_url': 'https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=800&auto=format&fit=crop',
        'organizer': 'CAF & FUFA Local Organizing Committee',
        'description': (
            'The opening blockbuster match of the 2027 Africa Cup of Nations '
            'East Africa Pamoja Bid edition in Kampala!'
        ),
        'featured': True,
    },
    {
        'id': 'evt_002',
        'public_id': 'pub_evt_crusade2026',
        'title': 'Great East Africa Crusade & Unity Festival 2026',
        'category': 'Religious',
        'location': 'Kololo Ceremonial Grounds, Kampala',
        'venue': 'Kololo Grounds Main Arena',
        'start_date': _iso('2026-09-20T08:00:00Z'),
        'end_date': _iso('2026-09-22T20:00:00Z'),
        'price_ugx': 0,
        'capacity': 60000,
        'registered_count': 42100,
        'image_url': 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=800&auto=format&fit=crop',
        'organizer': 'East Africa Inter-Religious Council',
        'description': (
            'A grand multi-nation festival celebrating peace, unity, and fan '
            'brotherhood leading into AFCON 2027.'
        ),
        'featured': True,
    },
    {
        'id': 'evt_003',
        'public_id': 'pub_evt_worldcup2026',
        'title': 'FIFA World Cup 2026 Fan Park & Live Screening',
        'category': 'Festival',
        'location': 'Lugogo Cricket Oval, Kampala',
        'venue': 'Lugogo Main Stage',
        'start_date': _iso('2026-06-25T18:00:00Z'),
        'end_date': _iso('2026-07-15T23:00:00Z'),
        'price_ugx': 25000,
        'capacity': 15000,
        'registered_count': 8900,
        'image_url': 'https://images.unsplash.com/photo-1518091043644-c1d4457512c6?w=800&auto=format&fit=crop',
        'organizer': 'AFCON360 Fan Zone Team',
        'description': (
            'Ultra-HD LED stadium screens, food stalls, live DJs, and '
            'interactive games during World Cup 2026 matches.'
        ),
        'featured': True,
    },
]


MOCK_EVENT_REGISTRATIONS: List[Dict[str, Any]] = [
    {
        'id': 'reg_001',
        'event_id': 'evt_001',
        'user_id': 'usr_fan1',
        'ticket_type': 'VIP Pass',
        'quantity': 2,
        'total_ugx': 150000,
        'qr_code': 'AFCON360-QR-98214-TKT',
        'status': 'confirmed',
        'created_at': _iso('2026-03-02T10:15:00Z'),
    },
]


MOCK_PROPERTIES: List[Dict[str, Any]] = [
    {
        'id': 'prop_001',
        'public_id': 'pub_prop_serena',
        'title': 'Kampala Serena Luxury Suite near Namboole Stadium Shuttle',
        'property_type': 'Hotel',
        'location': 'Central Kampala, Uganda',
        'address': 'Kintu Road, Kampala',
        'price_per_night_ugx': 450000,
        'rating': 4.9,
        'reviews_count': 128,
        'image_url': 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=800&auto=format&fit=crop',
        'host_name': 'Serena Hospitality',
        'amenities': ['Free WiFi', 'Swimming Pool', 'Airport Shuttle', 'AC', 'Breakfast Included'],
        'bedrooms': 2,
        'bathrooms': 2,
        'status': 'approved',
    },
    {
        'id': 'prop_002',
        'public_id': 'pub_prop_lake_breeze',
        'title': 'Ggaba Lake Victoria Breeze Penthouse',
        'property_type': 'Apartment',
        'location': 'Ggaba / Munyonyo, Kampala',
        'address': 'Plot 44 Lake Drive, Munyonyo',
        'price_per_night_ugx': 220000,
        'rating': 4.8,
        'reviews_count': 64,
        'image_url': 'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800&auto=format&fit=crop',
        'host_name': 'Grace Akello',
        'amenities': ['Lake View Balcony', 'Kitchen', 'Free Parking', 'Washing Machine'],
        'bedrooms': 3,
        'bathrooms': 2,
        'status': 'approved',
    },
    {
        'id': 'prop_003',
        'public_id': 'pub_prop_jinja_eco',
        'title': 'Source of the Nile Eco Resort Cottage',
        'property_type': 'Villa',
        'location': 'Jinja, Uganda',
        'address': 'Nile Crescent, Jinja',
        'price_per_night_ugx': 310000,
        'rating': 4.95,
        'reviews_count': 92,
        'image_url': 'https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?w=800&auto=format&fit=crop',
        'host_name': 'Jinja Adventure Stays',
        'amenities': ['River Kayaking', 'Solar Power', 'Restaurant', 'Garden View'],
        'bedrooms': 1,
        'bathrooms': 1,
        'status': 'approved',
    },
]


MOCK_PROPERTY_BOOKINGS: List[Dict[str, Any]] = [
    {
        'id': 'bk_001',
        'property_id': 'prop_002',
        'user_id': 'usr_fan1',
        'check_in': '2026-06-11',
        'check_out': '2026-06-14',
        'guests': 2,
        'total_ugx': 660000,
        'status': 'confirmed',
        'created_at': _iso('2026-03-01T12:00:00Z'),
    },
]


MOCK_VEHICLES: List[Dict[str, Any]] = [
    {
        'id': 'veh_001',
        'public_id': 'pub_veh_001',
        'name': 'Toyota Coaster Executive VIP Shuttle',
        'type': 'VIP Coaster Bus',
        'capacity': 28,
        'rate_per_km_ugx': 3500,
        'base_fare_ugx': 50000,
        'driver_name': 'John Kato',
        'plate_number': 'UBJ 482A',
        'status': 'available',
        'location': 'Entebbe International Airport / Kampala Central',
    },
    {
        'id': 'veh_002',
        'public_id': 'pub_veh_002',
        'name': 'Land Cruiser V8 VIP Convoy SUV',
        'type': 'Executive Sedan',
        'capacity': 4,
        'rate_per_km_ugx': 5000,
        'base_fare_ugx': 80000,
        'driver_name': 'Moses Opolot',
        'plate_number': 'UBG 901Z',
        'status': 'available',
        'location': 'Munyonyo Commonwealth Resort',
    },
    {
        'id': 'veh_003',
        'public_id': 'pub_veh_003',
        'name': 'AFCON Express Airport Transfer Van',
        'type': 'Airport Shuttle Van',
        'capacity': 12,
        'rate_per_km_ugx': 2800,
        'base_fare_ugx': 35000,
        'driver_name': 'Samuel Ssemwanga',
        'plate_number': 'UBL 112B',
        'status': 'available',
        'location': 'Entebbe Airport Terminal',
    },
]


MOCK_TRANSPORT_BOOKINGS: List[Dict[str, Any]] = [
    {
        'id': 'tbk_001',
        'vehicle_id': 'veh_001',
        'user_id': 'usr_fan1',
        'pickup_location': 'Entebbe International Airport',
        'dropoff_location': 'Kampala Serena Hotel',
        'pickup_time': '2026-06-11 14:00',
        'distance_km': 42,
        'total_ugx': 197000,
        'status': 'confirmed',
        'created_at': _iso('2026-03-02T11:00:00Z'),
    },
]


MOCK_KYC_SUBMISSIONS: List[Dict[str, Any]] = [
    {
        'id': 'kyc_001',
        'user_id': 'usr_fan1',
        'document_type': 'National ID',
        'document_number': 'CM98012345ABCD',
        'status': 'approved',
        'submitted_at': _iso('2026-01-16T10:00:00Z'),
        'reviewed_at': _iso('2026-01-16T11:30:00Z'),
        'reviewer_notes': 'National ID verified with NIRA database.',
    },
    {
        'id': 'kyc_002',
        'user_id': 'usr_host1',
        'document_type': 'Proof of Residence',
        'document_number': 'REG-PROPERTY-8842',
        'status': 'approved',
        'submitted_at': _iso('2026-01-11T09:00:00Z'),
        'reviewed_at': _iso('2026-01-11T10:15:00Z'),
        'reviewer_notes': 'Property deed verified.',
    },
]


# ---------------------------------------------------------------------------
# Notification templates (ported from src/notifications/templateService.ts)
# ---------------------------------------------------------------------------
# NOTE: `type` values intentionally map onto app.notifications.models.NotificationType
# so seeded rows satisfy the ck_notifications_type check constraint.

DEFAULT_NOTIFICATION_TEMPLATES: List[Dict[str, Any]] = [
    {
        'key': 'tmpl_booking_email',
        'type': 'booking_confirmed',
        'channel': 'email',
        'subject': 'AFCON360 Booking Confirmed: {{ item_name }}',
        'body_template': (
            'Dear {{ user_name }},\n\n'
            'Your booking for {{ item_name }} (Ref: {{ reference_id }}) has been confirmed!\n'
            'Total Paid / Escrow Held: UGX {{ total_ugx }}.\n'
            'Check-in / Date: {{ booking_date }}.\n\n'
            'Thank you for choosing AFCON360 East Africa Pamoja.'
        ),
        'html_template': (
            '<h2>Booking Confirmation</h2>'
            '<p>Dear <strong>{{ user_name }}</strong>,</p>'
            '<p>Your booking for <strong>{{ item_name }}</strong> '
            '(Ref: <code>{{ reference_id }}</code>) is confirmed.</p>'
            '<p>Total: <strong>UGX {{ total_ugx }}</strong></p>'
        ),
        'default_priority': 'high',
        'is_active': True,
    },
    {
        'key': 'tmpl_booking_sms',
        'type': 'booking_confirmed',
        'channel': 'sms',
        'subject': None,
        'body_template': (
            'AFCON360: Booking {{ reference_id }} for {{ item_name }} confirmed! '
            'Total UGX {{ total_ugx }}. Show this SMS or QR pass upon arrival.'
        ),
        'html_template': None,
        'default_priority': 'high',
        'is_active': True,
    },
    {
        'key': 'tmpl_booking_inapp',
        'type': 'booking_confirmed',
        'channel': 'in_app',
        'subject': 'Booking Confirmed: {{ item_name }}',
        'body_template': (
            'Your booking for {{ item_name }} is confirmed (Ref: {{ reference_id }}). '
            'Escrow funds held safely in your Fan Wallet.'
        ),
        'html_template': None,
        'default_priority': 'medium',
        'is_active': True,
    },
    {
        'key': 'tmpl_payment_email',
        'type': 'payment_received',
        'channel': 'email',
        'subject': 'AFCON360 Fan Wallet Receipt: UGX {{ amount }}',
        'body_template': (
            'Hello {{ user_name }},\n\n'
            'We have received your payment / deposit of UGX {{ amount }} via {{ payment_method }}.\n'
            'Tx Reference: {{ tx_ref }}.\n'
            'Updated Balance: UGX {{ new_balance }}.'
        ),
        'html_template': None,
        'default_priority': 'high',
        'is_active': True,
    },
    {
        'key': 'tmpl_payment_sms',
        'type': 'payment_received',
        'channel': 'sms',
        'subject': None,
        'body_template': (
            'AFCON360 Wallet: Received UGX {{ amount }} via {{ payment_method }}. '
            'Ref: {{ tx_ref }}. New Balance: UGX {{ new_balance }}.'
        ),
        'html_template': None,
        'default_priority': 'medium',
        'is_active': True,
    },
    {
        'key': 'tmpl_payment_inapp',
        'type': 'payment_received',
        'channel': 'in_app',
        'subject': 'Payment Receipt: UGX {{ amount }}',
        'body_template': (
            'Your wallet transaction of UGX {{ amount }} via {{ payment_method }} '
            'was successful. Tx Ref: {{ tx_ref }}.'
        ),
        'html_template': None,
        'default_priority': 'medium',
        'is_active': True,
    },
    {
        'key': 'tmpl_event_reminder_email',
        'type': 'event_reminder',
        'channel': 'email',
        'subject': 'Upcoming Event Alert: {{ event_title }} is Tomorrow!',
        'body_template': (
            'Hi {{ user_name }},\n\n'
            'This is a reminder that {{ event_title }} takes place at {{ venue }} '
            'on {{ event_date }}.\n'
            'Have your QR pass ready in your AFCON360 App.'
        ),
        'html_template': None,
        'default_priority': 'medium',
        'is_active': True,
    },
    {
        'key': 'tmpl_welcome_email',
        'type': 'verification_email',
        'channel': 'email',
        'subject': 'Welcome to AFCON360 - East Africa Tournament Portal',
        'body_template': (
            'Dear {{ user_name }},\n\n'
            'Welcome to AFCON360! Enjoy seamless match ticketing, luxury accommodation, '
            'VIP shuttles, and mobile money wallet integration.'
        ),
        'html_template': None,
        'default_priority': 'medium',
        'is_active': True,
    },
    {
        'key': 'tmpl_direct_message_inapp',
        'type': 'internal_message',
        'channel': 'in_app',
        'subject': 'New Message from {{ sender_name }}',
        'body_template': '{{ sender_name }}: {{ message_content }}',
        'html_template': None,
        'default_priority': 'high',
        'is_active': True,
    },
]


MOCK_NOTIFICATION_PREFERENCES: List[Dict[str, Any]] = [
    {'notification_type': 'booking_confirmed', 'channel': 'email', 'enabled': True},
    {'notification_type': 'booking_confirmed', 'channel': 'in_app', 'enabled': True},
    {'notification_type': 'booking_confirmed', 'channel': 'sms', 'enabled': False},
    {'notification_type': 'payment_received', 'channel': 'email', 'enabled': True},
    {'notification_type': 'payment_received', 'channel': 'in_app', 'enabled': True},
    {'notification_type': 'event_reminder', 'channel': 'email', 'enabled': True},
    {'notification_type': 'event_reminder', 'channel': 'push', 'enabled': True},
    {'notification_type': 'internal_message', 'channel': 'in_app', 'enabled': True},
]


MOCK_NOTIFICATIONS: List[Dict[str, Any]] = [
    {
        'type': 'booking_confirmed',
        'channel': 'in_app',
        'subject': 'Booking Confirmed: Ggaba Lake Victoria Breeze Penthouse',
        'body': (
            'Your booking for Ggaba Lake Victoria Breeze Penthouse is confirmed '
            '(Ref: bk_001). Escrow funds held safely in your Fan Wallet.'
        ),
        'priority': 'high',
        'status': 'sent',
        'is_read': False,
        'link': '/accommodation/bookings/bk_001',
        'context': {
            'item_name': 'Ggaba Lake Victoria Breeze Penthouse',
            'reference_id': 'bk_001',
            'total_ugx': 660000,
            'booking_date': '2026-06-11',
        },
    },
    {
        'type': 'payment_received',
        'channel': 'email',
        'subject': 'AFCON360 Fan Wallet Receipt: UGX 2000000',
        'body': (
            'We have received your payment / deposit of UGX 2000000 via MTN Mobile Money. '
            'Tx Reference: MTN_MOMO_982341.'
        ),
        'priority': 'high',
        'status': 'sent',
        'is_read': True,
        'link': '/wallet/transactions/pub_tx_001',
        'context': {
            'amount': 2000000,
            'payment_method': 'MTN Mobile Money',
            'tx_ref': 'MTN_MOMO_982341',
            'new_balance': 1850000,
        },
    },
    {
        'type': 'event_reminder',
        'channel': 'in_app',
        'subject': 'Upcoming Event Alert: AFCON 2027 Opener is Tomorrow!',
        'body': (
            'AFCON 2027 Opener: Uganda Cranes vs Kenya Harambee Stars takes place at '
            'Mandela National Stadium, Namboole. Have your QR pass ready.'
        ),
        'priority': 'normal',
        'status': 'pending',
        'is_read': False,
        'link': '/events/pub_evt_afcon2027',
        'context': {
            'event_title': 'AFCON 2027 Opener: Uganda Cranes vs Kenya Harambee Stars',
            'venue': 'Mandela National Stadium, Namboole',
            'event_date': '2027-06-12',
        },
    },
    {
        'type': 'internal_message',
        'channel': 'in_app',
        'subject': 'New Message from Grace Akello',
        'body': 'Grace Akello: Your penthouse check-in keys are ready at reception.',
        'priority': 'high',
        'status': 'sent',
        'is_read': False,
        'link': '/messages',
        'context': {
            'sender_name': 'Grace Akello',
            'message_content': 'Your penthouse check-in keys are ready at reception.',
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_mock_data() -> Dict[str, Any]:
    """Return a deep copy of every fixture group, keyed by domain."""
    return copy.deepcopy({
        'users': MOCK_USERS,
        'wallets': MOCK_WALLETS,
        'events': MOCK_EVENTS,
        'event_registrations': MOCK_EVENT_REGISTRATIONS,
        'properties': MOCK_PROPERTIES,
        'property_bookings': MOCK_PROPERTY_BOOKINGS,
        'vehicles': MOCK_VEHICLES,
        'transport_bookings': MOCK_TRANSPORT_BOOKINGS,
        'kyc_submissions': MOCK_KYC_SUBMISSIONS,
        'notification_templates': DEFAULT_NOTIFICATION_TEMPLATES,
        'notification_preferences': MOCK_NOTIFICATION_PREFERENCES,
        'notifications': MOCK_NOTIFICATIONS,
    })


def get_mock_user(identifier: str) -> Optional[Dict[str, Any]]:
    """Look up a mock user by ``id``, ``public_id``, ``username`` or ``email``."""
    for user in MOCK_USERS:
        if identifier in (
            user['id'], user['public_id'], user['username'], user['email']
        ):
            return copy.deepcopy(user)
    return None


def get_mock_wallet(user_id: str) -> Optional[Dict[str, Any]]:
    """Return the mock wallet for a mock user id."""
    wallet = MOCK_WALLETS.get(user_id)
    return copy.deepcopy(wallet) if wallet else None


def render_mock_template(template_str: str, context: Dict[str, Any]) -> str:
    """
    Render ``{{ placeholder }}`` tokens using the shared Jinja2 environment.

    Mirrors ``TemplateService.render`` from the legacy TypeScript service:
    missing keys collapse to an empty string rather than raising.
    """
    from app.notifications.template_loader import template_loader

    try:
        return template_loader.env.from_string(template_str).render(**(context or {}))
    except Exception:
        return template_str


def _template_defaults() -> Dict[str, Any]:
    return {'created_at': datetime.now(timezone.utc)}


def seed_mock_notification_data(
    db_session: Any = None,
    user_id: Optional[int] = None,
    include_templates: bool = True,
    include_preferences: bool = True,
    include_notifications: bool = True,
    commit: bool = True,
) -> Dict[str, Any]:
    """
    Seed realistic notification fixtures for local development and tests.

    Args:
        db_session: SQLAlchemy session. When ``None`` nothing is persisted and
            the raw fixture dictionaries are returned instead (dry run).
        user_id: Internal ``users.id`` to attach preferences/notifications to.
            Required to seed preferences and notifications.
        include_templates: Seed :class:`NotificationTemplate` rows.
        include_preferences: Seed :class:`UserNotificationPreference` rows.
        include_notifications: Seed :class:`Notification` + :class:`NotificationLog` rows.
        commit: Commit the session when finished. Set ``False`` inside tests
            that manage their own transaction.

    Returns:
        Dict describing what was created. On a dry run this is the full fixture
        payload from :func:`get_mock_data`.
    """
    if db_session is None:
        return get_mock_data()

    from app.notifications.models import (
        Notification,
        NotificationLog,
        NotificationTemplate,
        UserNotificationPreference,
    )

    created: Dict[str, List[Any]] = {
        'templates': [],
        'preferences': [],
        'notifications': [],
        'logs': [],
    }

    # --- Templates -------------------------------------------------------
    if include_templates:
        for spec in DEFAULT_NOTIFICATION_TEMPLATES:
            existing = (
                db_session.query(NotificationTemplate)
                .filter_by(type=spec['type'], channel=spec['channel'])
                .first()
            )
            if existing:
                created['templates'].append(existing)
                continue

            template = NotificationTemplate(
                type=spec['type'],
                channel=spec['channel'],
                subject=spec['subject'],
                body_template=spec['body_template'],
                html_template=spec['html_template'],
                default_priority=spec['default_priority'],
                is_active=spec['is_active'],
            )
            db_session.add(template)
            created['templates'].append(template)

    # --- Preferences -----------------------------------------------------
    if include_preferences and user_id:
        for spec in MOCK_NOTIFICATION_PREFERENCES:
            existing = (
                db_session.query(UserNotificationPreference)
                .filter_by(
                    user_id=user_id,
                    notification_type=spec['notification_type'],
                    channel=spec['channel'],
                )
                .first()
            )
            if existing:
                existing.enabled = spec['enabled']
                created['preferences'].append(existing)
                continue

            pref = UserNotificationPreference(
                user_id=user_id,
                notification_type=spec['notification_type'],
                channel=spec['channel'],
                enabled=spec['enabled'],
            )
            db_session.add(pref)
            created['preferences'].append(pref)

    # --- Notifications + delivery logs -----------------------------------
    if include_notifications and user_id:
        now = datetime.now(timezone.utc)
        user = None
        try:
            from app.identity.models.user import User
            user = db_session.get(User, user_id)
        except Exception:
            user = None

        for offset, spec in enumerate(MOCK_NOTIFICATIONS):
            sent_at = now - timedelta(hours=offset)
            # Enforce the same vocabularies as the Notification model validators
            # (Flask-side), and derive the required `module` column — which is
            # NOT NULL — from the type fallback so seed rows stay valid after the
            # module column migration.
            from app.notifications.models import (
                NotificationType,
                NotificationChannel,
                NotificationStatus,
                NotificationModule,
            )
            from app.notifications.services import NotificationService

            ntype = NotificationType(spec['type'])
            nchan = NotificationChannel(spec['channel'])
            nstat = NotificationStatus(spec['status'])
            nmod = NotificationService.TYPE_MODULE_FALLBACK.get(ntype.value, NotificationModule.SYSTEM)
            notification = Notification(
                user_id=user_id,
                email=getattr(user, 'email', None),
                phone=getattr(user, 'phone', None),
                type=ntype,
                module=nmod,
                channel=nchan,
                context=spec['context'],
                subject=spec['subject'],
                body=spec['body'],
                priority=spec['priority'],
                status=nstat,
                is_read=spec['is_read'],
                read_at=sent_at if spec['is_read'] else None,
                link=spec['link'],
                attempts=1 if spec['status'] != 'pending' else 0,
                sent_at=sent_at if spec['status'] != 'pending' else None,
                external_id=f"mock_{spec['type']}_{offset}",
            )
            db_session.add(notification)
            created['notifications'].append(notification)

            if spec['status'] != 'pending':
                db_session.flush()
                log = NotificationLog(
                    notification_id=notification.id,
                    channel=spec['channel'],
                    status='success',
                    response_code=200,
                    response_body='Mock delivery acknowledged.',
                    attempted_at=sent_at,
                )
                db_session.add(log)
                created['logs'].append(log)

    if commit:
        db_session.commit()
    else:
        db_session.flush()

    return {
        'templates': len(created['templates']),
        'preferences': len(created['preferences']),
        'notifications': len(created['notifications']),
        'logs': len(created['logs']),
        'objects': created,
    }


def clear_mock_notification_data(db_session: Any, user_id: Optional[int] = None) -> Dict[str, int]:
    """
    Remove fixtures created by :func:`seed_mock_notification_data`.

    Notifications/preferences are scoped to ``user_id`` when supplied; seeded
    templates are matched on their (type, channel) pairs.
    """
    from app.notifications.models import (
        Notification,
        NotificationLog,
        NotificationTemplate,
        UserNotificationPreference,
    )

    deleted = {'notifications': 0, 'logs': 0, 'preferences': 0, 'templates': 0}

    if user_id:
        notifications = (
            db_session.query(Notification)
            .filter(Notification.user_id == user_id)
            .filter(Notification.external_id.like('mock_%'))
            .all()
        )
        for notification in notifications:
            logs = (
                db_session.query(NotificationLog)
                .filter_by(notification_id=notification.id)
                .all()
            )
            for log in logs:
                db_session.delete(log)
                deleted['logs'] += 1
            db_session.delete(notification)
            deleted['notifications'] += 1

        for spec in MOCK_NOTIFICATION_PREFERENCES:
            pref = (
                db_session.query(UserNotificationPreference)
                .filter_by(
                    user_id=user_id,
                    notification_type=spec['notification_type'],
                    channel=spec['channel'],
                )
                .first()
            )
            if pref:
                db_session.delete(pref)
                deleted['preferences'] += 1

    for spec in DEFAULT_NOTIFICATION_TEMPLATES:
        template = (
            db_session.query(NotificationTemplate)
            .filter_by(type=spec['type'], channel=spec['channel'])
            .first()
        )
        if template:
            db_session.delete(template)
            deleted['templates'] += 1

    db_session.commit()
    return deleted
