"""Contract: the universal notification bell announces through the phone's
own notification centre (Web Notifications API — banner + OS sound).

The feature is client-side inside templates/components/notification_bell.html,
so these tests pin the shipped contract of that script:

  * permission is requested from a user gesture (bell click), never on load;
  * the system notification path carries an OS-sound-capable payload
    (tag + renotify) and a real icon asset;
  * banner content reuses the existing inbox API (no new backend surface);
  * arrivals are detected from the unread-count poll and work while the
    tab is hidden (backgrounded phones must still ring);
  * a denied permission degrades to silence, never an exception;
  * the one-shot init guard survives so multiple includes stay safe.
"""
from pathlib import Path

from flask_login import login_user

from app.extensions import db
from app.identity.models.user import User

import uuid

BELL_TEMPLATE = (
    Path(__file__).resolve().parents[2] / 'templates' / 'components' / 'notification_bell.html'
)


def _source() -> str:
    return BELL_TEMPLATE.read_text(encoding='utf-8')


class TestSystemNotifyContract:
    def test_permission_requested_from_user_gesture(self):
        src = _source()
        assert 'Notification.requestPermission()' in src
        # Asked through the bell-click path, not during script evaluation.
        assert 'askPermission(function () {' in src

    def test_denied_permission_degrades_to_silence(self):
        src = _source()
        assert "Notification.permission === 'granted'" in src
        assert "Notification.permission !== 'default'" in src

    def test_system_banner_carries_os_sound_payload(self):
        src = _source()
        assert 'new Notification(' in src
        assert 'renotify: true' in src
        assert 'tag: NOTIF_TAG' in src

    def test_icon_points_at_existing_asset(self):
        src = _source()
        assert '/static/icons/icon-192.png' in src
        icon = Path(__file__).resolve().parents[2] / 'static' / 'icons' / 'icon-192.png'
        assert icon.exists(), 'notification icon asset missing'

    def test_banner_content_reuses_existing_inbox_api(self):
        assert '/api/notifications?limit=1&unread_only=true' in _source()

    def test_arrival_detection_wired_to_unread_poll(self):
        src = _source()
        assert 'if (total > lastTotal) noticeFor(total - lastTotal, ' in src
        assert 'lastTotal = total;' in src

    def test_poll_runs_while_tab_is_hidden(self):
        # Backgrounded pages must keep announcing arrivals — the old
        # `if (document.hidden) return;` guard is deliberately gone.
        assert 'if (document.hidden) return;' not in _source()

    def test_service_worker_fallback_when_constructor_blocked(self):
        src = _source()
        assert 'showNotification' in src
        assert 'serviceWorker' in src

    def test_single_init_guard_preserved(self):
        src = _source()
        assert 'window.__afcNotifInit' in src


class TestBellRender:
    def test_bell_renders_with_system_notify_script(self, app):
        with app.app_context():
            user = User(
                email=f'bell_user_{uuid.uuid4().hex[:6]}@example.com',
                username=f'belluser_{uuid.uuid4().hex[:6]}',
                password_hash='hashed',
                is_active=True,
                is_verified=True,
            )
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with app.test_request_context('/'):
            from app.identity.models.user import User as UserModel

            user = db.session.get(UserModel, user_id)
            login_user(user)
            from flask import render_template

            html = render_template('components/notification_bell.html')

        assert 'afc-notif' in html
        assert 'Notification.requestPermission()' in html
        assert 'new Notification(' in html

    def test_linkless_item_falls_back_to_module_inbox(self, app):
        """SMALL-01 (P4): a notification without a deep link must land on
        the existing module-filtered inbox, never a dead '#'."""
        from datetime import datetime, timezone
        from types import SimpleNamespace

        with app.app_context():
            user = User(
                email=f'bell_p4_{uuid.uuid4().hex[:6]}@example.com',
                username=f'bellp4_{uuid.uuid4().hex[:6]}',
                password_hash='hashed',
                is_active=True,
                is_verified=True,
            )
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with app.test_request_context('/'):
            from app.identity.models.user import User as UserModel

            user = db.session.get(UserModel, user_id)
            login_user(user)
            from flask import render_template

            item = SimpleNamespace(
                id=4242, module='transport', link=None, is_read=False,
                subject='Ride update', type='ride_update', body='Driver nearby',
                created_at=datetime.now(timezone.utc),
            )
            html = render_template(
                'components/notification_bell.html',
                recent_notifications=[item],
                notif_badges={}, notif_modules=[],
            )

        assert 'href="#"' not in html
        assert '/notifications?module=transport' in html

    def test_linkless_system_item_falls_back_to_plain_inbox(self, app):
        """SMALL-01 verification (P4): link NULL + module system/None must
        land on the plain notifications inbox — valid route, no exception,
        no dead '#'."""
        from datetime import datetime, timezone
        from types import SimpleNamespace

        with app.app_context():
            user = User(
                email=f'bell_p4s_{uuid.uuid4().hex[:6]}@example.com',
                username=f'bellp4s_{uuid.uuid4().hex[:6]}',
                password_hash='hashed',
                is_active=True,
                is_verified=True,
            )
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with app.test_request_context('/'):
            from app.identity.models.user import User as UserModel

            user = db.session.get(UserModel, user_id)
            login_user(user)
            from flask import render_template

            def _item(i, module):
                return SimpleNamespace(
                    id=5000 + i, module=module, link=None, is_read=False,
                    subject='System note', type='system_note', body='hi',
                    created_at=datetime.now(timezone.utc),
                )

            html = render_template(
                'components/notification_bell.html',
                recent_notifications=[_item(1, 'system'), _item(2, None)],
                notif_badges={}, notif_modules=[],
            )

        assert 'href="#"' not in html
        assert 'href="/notifications"' in html
