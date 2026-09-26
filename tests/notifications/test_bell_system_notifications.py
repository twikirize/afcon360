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
