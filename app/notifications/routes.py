"""
AFCON360 Notification System - API Routes

Provides REST endpoints for:
- Notification inbox (list, unread count, mark read)
- User preferences (get, update, per-channel opt-out)
- Internal messaging (list, send, reply, archive)
- Admin communication settings (aggregators: Twilio, email, push, webhook)
- Dead-letter queue inspection & retry
- Broadcast / platform announcements

All routes respect the dual-ID system (public_id externally, id internally),
RBAC (owner/super_admin/admin), and soft-delete conventions.
"""

import logging
from typing import Dict, Any

from flask import Blueprint, jsonify, request, abort, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.notifications.models import (
    Notification,
    NotificationType,
    NotificationChannel,
    NotificationStatus,
    NotificationModule,
    Message,
    CommunicationSettings,
    NotificationAggregator,
)
from app.notifications.services import NotificationService
from app.notifications.preferences import PreferenceService
from app.auth.decorators import require_role, admin_required
from app.identity.models.user import User

logger = logging.getLogger(__name__)

notifications_api = Blueprint('notifications_api', __name__, url_prefix='/api/notifications')


# ============================================================================
# NOTIFICATION INBOX
# ============================================================================

@notifications_api.route('', methods=['GET'])
@login_required
def list_notifications():
    """List notifications for the current user.

    Query params:
        unread_only (bool), type (str), module (str, repeatable), limit (int), offset (int)

    `module` scopes the inbox to a single business (accommodation, transport,
    events, wallet, tourism, ...). These are separate modules with different
    customers, so a module dashboard should always pass it.
    """
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    ntype = request.args.get('type')
    modules = request.args.getlist('module') or (
        [request.args.get('module')] if request.args.get('module') else []
    )
    limit = min(int(request.args.get('limit', 20)), 100)
    offset = int(request.args.get('offset', 0))

    query = Notification.query.filter_by(user_id=current_user.id)
    if unread_only:
        query = query.filter_by(is_read=False)
    if ntype:
        try:
            query = query.filter_by(type=NotificationType(ntype))
        except ValueError:
            return jsonify({'error': 'Invalid notification type'}), 400
    if modules:
        valid = {m.value for m in NotificationModule}
        invalid = [m for m in modules if m not in valid]
        if invalid:
            return jsonify({
                'error': 'Invalid module(s): ' + ', '.join(invalid),
                'valid_modules': sorted(valid),
            }), 400
        query = query.filter(Notification.module.in_(modules))

    total = query.count()
    items = (
        query.order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return jsonify({
        'total': total,
        'count': len(items),
        'unread_count': NotificationService.get_unread_count(current_user.id),
        'unread_by_module': NotificationService.get_unread_counts_by_module(current_user.id),
        'modules': modules or None,
        'items': [_serialize_notification(n) for n in items],
    })


@notifications_api.route('/unread-count', methods=['GET'])
@login_required
def unread_count():
    """Unread badge count.

    Pass `?module=transport` to scope the badge to one business, or
    `?by_module=true` to get the full per-module breakdown for tabbed UIs.
    """
    module = request.args.get('module')
    if module and module not in {m.value for m in NotificationModule}:
        return jsonify({'error': 'Invalid module'}), 400

    payload = {
        'unread_count': NotificationService.get_unread_count(current_user.id, module=module),
        'module': module,
    }
    if request.args.get('by_module', 'false').lower() == 'true' or not module:
        payload['unread_by_module'] = NotificationService.get_unread_counts_by_module(current_user.id)
    return jsonify(payload)


@notifications_api.route('/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_read(notification_id):
    """Mark a single notification as read."""
    ok = NotificationService.mark_read(notification_id, current_user.id)
    if not ok:
        abort(404)
    return jsonify({'success': True, 'unread_count': NotificationService.get_unread_count(current_user.id)})


@notifications_api.route('/<int:notification_id>/unread', methods=['POST'])
@login_required
def mark_unread(notification_id):
    if not NotificationService.set_read_state(notification_id, current_user.id, False):
        abort(404)
    return jsonify({'success': True})


@notifications_api.route('/<int:notification_id>/important', methods=['POST'])
@login_required
def toggle_important(notification_id):
    data = request.get_json(silent=True) or {}
    is_important = bool(data.get('is_important', True))
    if not NotificationService.set_important(notification_id, current_user.id, is_important):
        abort(404)
    return jsonify({'success': True, 'is_important': is_important})


@notifications_api.route('/read-all', methods=['POST'])
@login_required
def mark_all_read():
    """Mark all notifications as read."""
    count = NotificationService.mark_all_read(current_user.id)
    return jsonify({'success': True, 'marked': count})


@notifications_api.route('/<int:notification_id>', methods=['DELETE'])
@login_required
def delete_notification(notification_id):
    """Soft-delete a notification (hide from inbox)."""
    n = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first()
    if not n:
        abort(404)
    n.soft_delete()
    db.session.commit()
    return jsonify({'success': True})


# ============================================================================
# USER PREFERENCES
# ============================================================================

@notifications_api.route('/preferences', methods=['GET'])
@login_required
def get_preferences():
    """Get the current user's notification preferences."""
    prefs = PreferenceService.get_all_for_user(current_user.id)
    return jsonify({
        'user_id': current_user.public_id,
        'preferences': prefs,
        'channels': [c.value for c in NotificationChannel],
        'types': [t.value for t in NotificationType],
        'modules': [m.value for m in NotificationModule],
    })


@notifications_api.route('/preferences', methods=['PUT', 'POST'])
@login_required
def update_preferences():
    """Update the current user's notification preferences.

    Body (JSON):
        [
          {"notification_type": "booking_confirmed", "channel": "email", "enabled": false},
          {"notification_type": "wallet_receipt", "channel": "sms", "enabled": true}
        ]
    """
    data = request.get_json(silent=True)
    if not isinstance(data, list):
        return jsonify({'error': 'Expected a list of preference objects'}), 400

    updated = PreferenceService.bulk_update(current_user.id, data)
    return jsonify({'success': True, 'updated': len(updated)})


@notifications_api.route('/preferences/channel', methods=['POST'])
@login_required
def set_channel_enabled():
    """Enable/disable an entire channel for the user (e.g. turn off all SMS)."""
    data = request.get_json(silent=True) or {}
    channel = data.get('channel')
    enabled = bool(data.get('enabled', True))
    if channel not in [c.value for c in NotificationChannel]:
        return jsonify({'error': 'Invalid channel'}), 400
    PreferenceService.set_channel_enabled(current_user.id, channel, enabled)
    return jsonify({'success': True, 'channel': channel, 'enabled': enabled})


# ============================================================================
# INTERNAL MESSAGING
# ============================================================================

@notifications_api.route('/messages', methods=['GET'])
@login_required
def list_messages():
    """List messages for the current user (inbox + sent)."""
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    direction = request.args.get('direction')
    limit = min(int(request.args.get('limit', 20)), 100)
    messages = NotificationService.get_user_messages(
        current_user.id, limit=limit, unread_only=unread_only, direction=direction
    )
    return jsonify({'count': len(messages), 'messages': [_serialize_message(m) for m in messages]})


@notifications_api.route('/messages', methods=['POST'])
@login_required
def send_message():
    """Send an internal message.

    Body (JSON):
        recipient_public_id (required), subject, body, message_type, parent_id (optional)
    """
    data = request.get_json(silent=True) or {}
    recipient_pid = data.get('recipient_public_id')
    subject = data.get('subject', 'Message')
    body = data.get('body', '')
    message_type = data.get('message_type', 'in_app')
    parent_id = data.get('parent_id')

    if not recipient_pid or not body:
        return jsonify({'error': 'recipient_public_id and body are required'}), 400

    recipient = User.query.filter_by(public_id=recipient_pid).first()
    if not recipient:
        return jsonify({'error': 'Recipient not found'}), 404

    message = NotificationService.send_internal_message(
        sender_id=current_user.id,
        recipient_id=recipient.id,
        subject=subject,
        body=body,
        message_type=message_type,
        direction='inbound',
        parent_id=parent_id,
    )
    if not message:
        return jsonify({'error': 'Failed to send message'}), 500

    return jsonify({'success': True, 'message': _serialize_message(message)}), 201


@notifications_api.route('/messages/<int:message_id>/read', methods=['POST'])
@login_required
def mark_message_read(message_id):
    ok = NotificationService.mark_message_read(message_id, current_user.id)
    if not ok:
        abort(404)
    return jsonify({'success': True})


@notifications_api.route('/messages/<int:message_id>/archive', methods=['POST'])
@login_required
def archive_message(message_id):
    ok = NotificationService.archive_message(message_id, current_user.id)
    if not ok:
        abort(404)
    return jsonify({'success': True})


# ============================================================================
# ADMIN COMMUNICATION SETTINGS (Aggregators & Channels)
# ============================================================================

@notifications_api.route('/admin/settings', methods=['GET'])
@login_required
@require_role('owner', 'super_admin', 'admin')
def admin_comm_settings():
    """Get all communication provider settings (redacted secrets)."""
    settings = CommunicationSettings.query.filter_by(is_deleted=False).all()
    aggregators = NotificationAggregator.query.filter_by(is_deleted=False).all()
    return jsonify({
        'providers': [_serialize_comm_setting(s) for s in settings],
        'aggregators': [_serialize_aggregator(a) for a in aggregators],
        'channels': [c.value for c in NotificationChannel],
    })


@notifications_api.route('/admin/settings', methods=['POST', 'PUT'])
@login_required
@require_role('owner', 'super_admin', 'admin')
def upsert_comm_setting():
    """Create or update a communication provider setting.

    Body (JSON):
        key (str), channel (str), provider (str), enabled (bool),
        config (JSON, may contain secrets), description (str)
    """
    data = request.get_json(silent=True) or {}
    key = data.get('key')
    if not key:
        return jsonify({'error': 'key is required'}), 400

    setting = CommunicationSettings.query.filter_by(key=key, is_deleted=False).first()
    if not setting:
        setting = CommunicationSettings(key=key)
        db.session.add(setting)

    setting.channel = data.get('channel', setting.channel)
    setting.provider = data.get('provider', setting.provider)
    setting.enabled = bool(data.get('enabled', setting.enabled))
    setting.config = data.get('config', setting.config or {})
    setting.description = data.get('description', setting.description)
    setting.updated_by = current_user.id
    db.session.commit()

    return jsonify({'success': True, 'setting': _serialize_comm_setting(setting)})


@notifications_api.route('/admin/settings/<int:setting_id>/toggle', methods=['POST'])
@login_required
@require_role('owner', 'super_admin', 'admin')
def toggle_comm_setting(setting_id):
    """Toggle a provider/channel on or off."""
    setting = CommunicationSettings.query.filter_by(id=setting_id, is_deleted=False).first()
    if not setting:
        abort(404)
    setting.enabled = not setting.enabled
    setting.updated_by = current_user.id
    db.session.commit()
    return jsonify({'success': True, 'enabled': setting.enabled})


@notifications_api.route('/admin/aggregators', methods=['POST', 'PUT'])
@login_required
@require_role('owner', 'super_admin', 'admin')
def upsert_aggregator():
    """Register an external aggregator (Twilio, SendGrid, FCM, WhatsApp, etc.).

    Body (JSON):
        name, provider_type, channels (list), enabled, credentials (JSON, secret),
        webhook_url, priority (int)
    """
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name:
        return jsonify({'error': 'name is required'}), 400

    agg = NotificationAggregator.query.filter_by(name=name, is_deleted=False).first()
    if not agg:
        agg = NotificationAggregator(name=name)
        db.session.add(agg)

    agg.provider_type = data.get('provider_type', agg.provider_type)
    agg.channels = data.get('channels', agg.channels or [])
    agg.enabled = bool(data.get('enabled', agg.enabled))
    agg.credentials = data.get('credentials', agg.credentials or {})
    agg.webhook_url = data.get('webhook_url', agg.webhook_url)
    agg.priority = int(data.get('priority', agg.priority or 10))
    agg.updated_by = current_user.id
    db.session.commit()

    return jsonify({'success': True, 'aggregator': _serialize_aggregator(agg)})


@notifications_api.route('/admin/aggregators/<int:agg_id>/test', methods=['POST'])
@login_required
@require_role('owner', 'super_admin', 'admin')
def test_aggregator(agg_id):
    """Send a test message via an aggregator to verify configuration."""
    from app.notifications.integrations import dispatch_via_aggregator
    agg = NotificationAggregator.query.filter_by(id=agg_id, is_deleted=False).first()
    if not agg:
        abort(404)
    result = dispatch_via_aggregator(agg, test=True)
    return jsonify({'success': result.get('ok', False), 'detail': result})


# ============================================================================
# DEAD-LETTER QUEUE & RETRIES (Admin)
# ============================================================================

@notifications_api.route('/admin/dead-letter', methods=['GET'])
@login_required
@require_role('owner', 'super_admin', 'admin')
def dead_letter_queue():
    """Inspect failed notifications (dead-letter candidates)."""
    failed = (
        Notification.query.filter_by(status=NotificationStatus.FAILED)
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify({
        'count': len(failed),
        'items': [_serialize_notification(n) for n in failed],
    })


@notifications_api.route('/admin/resend-failed', methods=['POST'])
@login_required
@require_role('owner', 'super_admin', 'admin')
def resend_failed():
    """Trigger a resend of all failed notifications."""
    from app.notifications.tasks import resend_failed_task
    result = resend_failed_task.delay() if _celery_available() else resend_failed_task()
    return jsonify({'success': True, 'task': str(result)})


@notifications_api.route('/admin/broadcast', methods=['POST'])
@login_required
@require_role('owner', 'super_admin', 'admin')
def broadcast():
    """Send a platform announcement to all (or role-filtered) users."""
    data = request.get_json(silent=True) or {}
    title = data.get('title')
    message = data.get('message')
    roles = data.get('roles', [])  # empty = all users
    channels = data.get('channels', ['in_app', 'email'])

    if not title or not message:
        return jsonify({'error': 'title and message required'}), 400

    count = NotificationService.broadcast_announcement(
        title=title, message=message, roles=roles, channels=channels,
        sender_id=current_user.id,
    )
    return jsonify({'success': True, 'recipients': count})


# ============================================================================
# SERIALIZERS
# ============================================================================

def _serialize_notification(n: Notification) -> Dict[str, Any]:
    return {
        'id': n.id,
        'public_id': getattr(n, 'public_id', None),
        'type': n.type,
        'module': n.module,
        'module_label': n.module_label,
        'module_icon': n.module_icon,
        'module_color': n.module_color,
        'channel': n.channel,
        'subject': n.subject,
        'body': n.body,
        'priority': n.priority,
        'status': n.status,
        'is_read': n.is_read,
        'is_important': n.is_important,
        'read_at': n.read_at.isoformat() if n.read_at else None,
        'created_at': n.created_at.isoformat() if n.created_at else None,
        'link': getattr(n, 'link', None),
        'external_id': n.external_id,
    }


def _serialize_message(m: Message) -> Dict[str, Any]:
    return {
        'id': m.id,
        'sender_id': m.sender_id,
        'recipient_id': m.recipient_id,
        'subject': m.subject,
        'body': m.body,
        'message_type': m.message_type,
        'direction': m.direction,
        'is_read': m.is_read,
        'read_at': m.read_at.isoformat() if m.read_at else None,
        'created_at': m.created_at.isoformat() if m.created_at else None,
        'parent_id': m.parent_id,
    }


def _serialize_comm_setting(s: CommunicationSettings) -> Dict[str, Any]:
    return {
        'id': s.id,
        'key': s.key,
        'channel': s.channel,
        'provider': s.provider,
        'enabled': s.enabled,
        'description': s.description,
        'config': _redact_config(s.config),
        'updated_at': s.updated_at.isoformat() if s.updated_at else None,
    }


def _serialize_aggregator(a: NotificationAggregator) -> Dict[str, Any]:
    return {
        'id': a.id,
        'name': a.name,
        'provider_type': a.provider_type,
        'channels': a.channels,
        'enabled': a.enabled,
        'webhook_url': a.webhook_url,
        'priority': a.priority,
        'credentials': _redact_config(a.credentials),
        'updated_at': a.updated_at.isoformat() if a.updated_at else None,
    }


def _redact_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Redact secret fields for API responses."""
    if not cfg:
        return {}
    secret_keys = ('api_key', 'secret', 'token', 'password', 'private_key', 'auth_token', 'account_sid')
    return {k: ('***REDACTED***' if any(s in k.lower() for s in secret_keys) else v) for k, v in cfg.items()}


def _celery_available() -> bool:
    try:
        from app.celery_app import celery_app
        return celery_app is not None
    except Exception:
        return False
