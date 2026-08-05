import os, uuid
os.environ['FLASK_ENV'] = 'testing'
os.environ['APP_ENV'] = 'testing'
from datetime import date, timedelta
from decimal import Decimal
from app import create_app
from app.extensions import db
from app.identity.models.user import User
from app.notifications.services import NotificationService
from app.notifications.channel_handlers import EmailHandler, InAppHandler

app = create_app()
with app.app_context():
    u = User(email='t-%s@example.com' % uuid.uuid4().hex[:6], username='t-%s' % uuid.uuid4().hex[:6],
             password_hash='x', email_verified=True, phone_verified=True, kyc_level=2)
    db.session.add(u); db.session.commit()
    print('user email:', u.email, 'id:', u.id)

    # test handlers directly
    class FakeNotif:
        id = 1
        subject = 'S'
        title = 'T'
    try:
        print('email validate:', EmailHandler().validate_recipient({'email': u.email}))
        print('email deliver:', EmailHandler().deliver(FakeNotif(), {'email': u.email}))
    except Exception as e:
        print('EMAIL HANDLER RAISED:', repr(e))
    try:
        print('inapp validate:', InAppHandler().validate_recipient({'user_id': u.id}))
        print('inapp deliver:', InAppHandler().deliver(FakeNotif(), {'user_id': u.id}))
    except Exception as e:
        print('INAPP HANDLER RAISED:', repr(e))

    # test send directly
    try:
        n = NotificationService.send(
            user_id=u.id, notification_type='booking_confirmed',
            title='Direct Test', message='hello', channels=['email', 'in_app'])
        print('SEND returned:', n)
        if n:
            print('  status:', n.status, 'last_error:', n.last_error, 'error_message:', n.error_message)
    except Exception as e:
        print('SEND RAISED:', repr(e))
