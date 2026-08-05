import os, uuid
os.environ['FLASK_ENV'] = 'testing'
os.environ['APP_ENV'] = 'testing'
from datetime import date, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.identity.models.user import User
from app.accommodation.models.property import Property, AccommodationCancellationPolicy
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus, AccommodationPaymentStatus
from app.accommodation.models.booking_policy import PropertyBookingPolicy
from app.accommodation.services.booking_service import BookingService
from app.notifications.signals import booking_confirmed
from app.notifications.services import NotificationService

app = create_app()
with app.app_context():
    # minimal host/guest/property
    host = User(email='h-%s@example.com' % uuid.uuid4().hex[:6], username='h-%s' % uuid.uuid4().hex[:6],
                password_hash='x', email_verified=True, phone_verified=True, kyc_level=2)
    guest = User(email='g-%s@example.com' % uuid.uuid4().hex[:6], username='g-%s' % uuid.uuid4().hex[:6],
                 password_hash='x', email_verified=True, phone_verified=True, kyc_level=2)
    db.session.add_all([host, guest]); db.session.commit()

    prop = Property(title='Test Property', slug='t-%s' % uuid.uuid4().hex[:8], description='d',
                   address_line1='1 St', city='Kampala', country='UG', status='active',
                   is_verified=True, is_active=True, base_price_per_night=Decimal('100.00'),
                   currency='USD', max_guests=4, instant_book=True,
                   cancellation_policy=AccommodationCancellationPolicy.FLEXIBLE.value, owner_user_id=host.id)
    db.session.add(prop); db.session.commit()
    pol = PropertyBookingPolicy(property_id=prop.id, cancellation_policy='flexible', free_cancel_hours=24,
                               require_payment_guarantee=True, reservation_hold_minutes=15,
                               allow_pay_now=True, allow_deposit_payment=True, allow_pay_on_arrival=False)
    db.session.add(pol); db.session.commit()

    print('listeners connected to booking_confirmed:', len(booking_confirmed.receivers))

    booking, err = BookingService.create_booking(
        property_id=prop.id, guest_user_id=guest.id, host_user_id=host.id,
        check_in=date.today() + timedelta(days=5), check_out=date.today() + timedelta(days=7),
        num_guests=2, guest_name='G', guest_email=guest.email, booking_type='self',
        booked_by_user_id=guest.id, payment_method='wallet', payment_timing='pay_now',
        payment_guaranteed=True, guarantee_type='wallet_balance')
    print('create_booking err:', err, 'status:', booking.status if booking else None)

    try:
        ok, msg = BookingService.confirm_booking(booking.id, wallet_transaction_id='txn-x')
        print('confirm_booking:', ok, msg)
    except Exception as e:
        print('CONFIRM RAISED:', repr(e))

    try:
        NotificationService.notify_booking_confirmed(booking)
        print('direct notify_booking_confirmed OK')
    except Exception as e:
        print('DIRECT notify RAISED:', repr(e))

    from app.notifications.models import Notification
    print('Notification count after flow:', Notification.query.count())
    for n in Notification.query.all():
        print('  -> user_id=%s type=%s channel=%s status=%s subj=%r err=%r' % (
            n.user_id, n.type, n.channel, n.status, n.subject, (n.last_error or n.error_message)))
