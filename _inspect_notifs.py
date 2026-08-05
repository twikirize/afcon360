import os
os.environ['FLASK_ENV'] = 'testing'
os.environ['APP_ENV'] = 'testing'
from app import create_app
from app.extensions import db
from app.notifications.models import Notification
from app.identity.models.user import User

app = create_app()
with app.app_context():
    rows = (
        db.session.query(Notification, User.email)
        .outerjoin(User, Notification.user_id == User.id)
        .order_by(Notification.id)
        .all()
    )
    print('TOTAL notifications:', len(rows))
    print('-' * 100)
    for n, email in rows:
        ctx = n.context or {}
        print('id=%s -> user_id=%s (%s)' % (n.id, n.user_id, email))
        print('    type=%s  channel=%s  status=%s  priority=%s' % (
            n.type.value, n.channel.value, n.status.value, n.priority))
        print('    subject=%r' % n.subject)
        print('    booking_id=%s  link=%s' % (ctx.get('booking_id'), n.link))
    print('-' * 100)
    byuser = {}
    for n, email in rows:
        key = email or ('user_%s' % n.user_id)
        byuser[key] = byuser.get(key, 0) + 1
    print('Notifications per recipient:')
    for k, v in byuser.items():
        print('  %s: %s' % (k, v))
