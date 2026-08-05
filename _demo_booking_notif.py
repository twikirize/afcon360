import os, uuid
os.environ['FLASK_ENV'] = 'testing'
os.environ['APP_ENV'] = 'testing'
from datetime import date, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.identity.models.user import User
from app.accommodation.models.property import Property, AccommodationCancellationPolicy
from app.accommodation.models.booking import AccommodationBookingStatus, AccommodationPaymentStatus
from app.accommodation.models.booking_policy import PropertyBookingPolicy
from app.accommodation.services.booking_service import BookingService
from app.notifications.models import Notification

app = create_app()
with app.app_context():
    # clean slate for a clear demo
    from app.notifications.models import NotificationLog
    NotificationLog.query.delete()
    Notification.query.delete()
    db.session.commit()

    host = User(email='host-%s@example.com' % uuid.uuid4().hex[:6], username='host-%s' % uuid.uuid4().hex[:6],
                password_hash='x', email_verified=True, phone_verified=True, kyc_level=2)
    guest = User(email='guest-%s@example.com' % uuid.uuid4().hex[:6], username='guest-%s' % uuid.uuid4().hex[:6],
                 password_hash='x', email_verified=True, phone_verified=True, kyc_level=2)
    db.session.add_all([host, guest]); db.session.commit()
    roles = {host.id: 'HOST', guest.id: 'GUEST'}

    prop = Property(title='Test Property', slug='t-%s' % uuid.uuid4().hex[:8], description='d',
                   address_line1='1 St', city='Kampala', country='UG', status='active',
                   is_verified=True, is_active=True, base_price_per_night=Decimal('100.00'),
                   currency='USD', max_guests=4, instant_book=True,
                   cancellation_policy=AccommodationCancellationPolicy.FLEXIBLE.value, owner_user_id=host.id)
    db.session.add(prop); db.session.commit()
    db.session.add(PropertyBookingPolicy(property_id=prop.id, cancellation_policy='flexible', free_cancel_hours=24,
                                        require_payment_guarantee=True, reservation_hold_minutes=15,
                                        allow_pay_now=True, allow_deposit_payment=True, allow_pay_on_arrival=False))
    db.session.commit()

    print('=' * 90)
    print('SCENARIO 1: INSTANT BOOK  ->  create + confirm')
    print('=' * 90)
    b1, err = BookingService.create_booking(
        property_id=prop.id, guest_user_id=guest.id, host_user_id=host.id,
        check_in=date.today() + timedelta(days=5), check_out=date.today() + timedelta(days=7),
        num_guests=2, guest_name='G', guest_email=guest.email, booking_type='self',
        booked_by_user_id=guest.id, payment_method='wallet', payment_timing='pay_now',
        payment_guaranteed=True, guarantee_type='wallet_balance')
    ok, msg = BookingService.confirm_booking(b1.id, wallet_transaction_id='txn-1')
    print('confirm_booking ->', ok, msg, '| booking status:', b1.status)

    print()
    print('SCENARIO 2: REQUEST-TO-BOOK  ->  create + host APPROVE')
    print('-' * 90)
    prop2 = Property(title='RTB Property', slug='rtb-%s' % uuid.uuid4().hex[:8], description='d',
                     address_line1='2 St', city='Kampala', country='UG', status='active',
                     is_verified=True, is_active=True, base_price_per_night=Decimal('150.00'),
                     currency='USD', max_guests=2, instant_book=False, require_host_approval=True,
                     cancellation_policy=AccommodationCancellationPolicy.MODERATE.value, owner_user_id=host.id)
    db.session.add(prop2); db.session.commit()
    db.session.add(PropertyBookingPolicy(property_id=prop2.id, cancellation_policy='moderate', free_cancel_hours=48,
                                        require_payment_guarantee=True, reservation_hold_minutes=15,
                                        allow_pay_now=True, allow_deposit_payment=True, allow_pay_on_arrival=False))
    db.session.commit()
    b2, err = BookingService.create_booking(
        property_id=prop2.id, guest_user_id=guest.id, host_user_id=host.id,
        check_in=date.today() + timedelta(days=9), check_out=date.today() + timedelta(days=11),
        num_guests=2, guest_name='G2', guest_email=guest.email, booking_type='self',
        booked_by_user_id=guest.id, payment_method='wallet', payment_timing='pay_now',
        payment_guaranteed=True, guarantee_type='wallet_balance')
    print('after create -> booking status:', b2.status, '(pending host approval)')
    ok, msg = BookingService.approve_booking(b2.id, approved_by_user_id=host.id, reason='Looks good')
    print('approve_booking ->', ok, msg, '| booking status:', b2.status)

    print()
    print('=' * 90)
    print('NOTIFICATIONS CREATED (recipient targets + channels + status)')
    print('=' * 90)
    rows = (db.session.query(Notification).order_by(Notification.id)).all()
    for n in rows:
        role = roles.get(n.user_id, '?')
        print('  -> %-5s user_id=%s  type=%-17s channel=%-7s status=%-9s %r'
              % (role, n.user_id, n.type, n.channel, n.status, n.subject))
    print()
    print('TOTAL notifications created:', len(rows))
