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
from app.notifications.settings import CommunicationSettingsService
from app.utils.log_redaction import register_secret_mapping
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
    import hashlib
    module = request.args.get('module')
    if module and module not in {m.value for m in NotificationModule}:
        return jsonify({'error': 'Invalid module'}), 400

    unread_count = NotificationService.get_unread_count(current_user.id, module=module)
    
    payload = {
        'unread_count': unread_count,
        'module': module,
    }
    if request.args.get('by_module', 'false').lower() == 'true' or not module:
        by_module = NotificationService.get_unread_counts_by_module(current_user.id)
        payload['unread_by_module'] = by_module
    else:
        by_module = {}

    # ETag for conditional requests
    etag = hashlib.md5(f"{unread_count}:{hash(frozenset(by_module.items()))}".encode()).hexdigest()

    if request.headers.get('If-None-Match') == etag:
        return '', 304

    resp = jsonify(payload)
    resp.headers['ETag'] = etag
    resp.headers['Cache-Control'] = 'private, max-age=5'
    return resp


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
@require_role('owner', 'super_admin')
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
@require_role('owner', 'super_admin')
def upsert_comm_setting():
    """Create or update a communication provider setting.

    Body (JSON):
        key (str), channel (str), provider (str), enabled (bool),
        config (JSON, may contain secrets), description (str)
    """
    data = request.get_json(silent=True) or {}
    key = data.get('key')
    channel = data.get('channel')
    config = data.get('config')
    if not key or not channel:
        return jsonify({'error': 'key and channel are required'}), 400
    if config is not None and not isinstance(config, dict):
        return jsonify({'error': 'config must be an object'}), 400

    try:
        setting = CommunicationSettingsService.upsert_setting(
            key=key,
            channel=channel,
            provider=data.get('provider'),
            enabled=data.get('enabled'),
            config=config,
            description=data.get('description'),
            updated_by=current_user.id,
            clear_secret_keys=data.get('clear_secret_keys') or [],
        )
    except Exception as exc:
        db.session.rollback()
        logger.error(
            "Communication provider setting was not saved (exception_type=%s)",
            type(exc).__name__,
        )
        return jsonify({'error': 'Provider configuration could not be saved securely'}), 503

    return jsonify({'success': True, 'setting': _serialize_comm_setting(setting)})


@notifications_api.route('/admin/settings/<int:setting_id>/toggle', methods=['POST'])
@login_required
@require_role('owner', 'super_admin')
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
@require_role('owner', 'super_admin')
def upsert_aggregator():
    """Register an external aggregator (Twilio, SendGrid, FCM, WhatsApp, etc.).

    Body (JSON):
        name, provider_type, channels (list), enabled, credentials (JSON, secret),
        webhook_url, priority (int)
    """
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    provider_type = data.get('provider_type')
    channels = data.get('channels')
    credentials = data.get('credentials')
    if not name or not provider_type or not isinstance(channels, list):
        return jsonify({'error': 'name, provider_type and channels are required'}), 400
    if credentials is not None and not isinstance(credentials, dict):
        return jsonify({'error': 'credentials must be an object'}), 400

    try:
        agg = CommunicationSettingsService.upsert_aggregator(
            name=name,
            provider_type=provider_type,
            channels=channels,
            enabled=data.get('enabled'),
            credentials=credentials,
            webhook_url=data.get('webhook_url'),
            clear_webhook_url=bool(data.get('clear_webhook_url')),
            priority=int(data.get('priority', 10)),
            updated_by=current_user.id,
        )
    except Exception as exc:
        db.session.rollback()
        logger.error(
            "Communication aggregator was not saved (exception_type=%s)",
            type(exc).__name__,
        )
        return jsonify({'error': 'Aggregator credentials could not be saved securely'}), 503

    return jsonify({'success': True, 'aggregator': _serialize_aggregator(agg)})


@notifications_api.route('/admin/aggregators/<int:agg_id>/test', methods=['POST'])
@login_required
@require_role('owner', 'super_admin')
def test_aggregator(agg_id):
    """Send a test message via an aggregator to verify configuration."""
    from app.notifications.integrations import dispatch_via_aggregator
    agg = NotificationAggregator.query.filter_by(id=agg_id, is_deleted=False).first()
    if not agg:
        abort(404)
    result = dispatch_via_aggregator(agg, test=True)
    return jsonify({'success': result.get('ok', False), 'detail': result})


def _missing_initial_smtp_credentials(data, environment_config, existing_setting):
    """Require explicit re-entry before replacing an environment-only SMTP config.

    Once an Owner-managed row exists, blank secret fields mean preserve the
    encrypted database value. Before the first row exists, however, a blank
    field would silently discard an environment credential when the database
    row becomes authoritative. Require explicit entry for each configured
    environment credential, unless the Owner explicitly clears authentication.
    """
    if existing_setting is not None or data.get('clear_auth'):
        return []

    missing = []
    for field, env_key, label in (
        ('smtp_user', 'MAIL_USERNAME', 'SMTP username'),
        ('smtp_pass', 'MAIL_PASSWORD', 'SMTP password'),
    ):
        if environment_config.get(env_key) and not str(data.get(field) or '').strip():
            missing.append(label)
    return missing


def _smtp_auth_pair_error(data, existing_config):
    """Validate the effective SMTP auth pair after blank-secret preservation."""
    supplied_user = data.get('smtp_user')
    supplied_pass = data.get('smtp_pass')

    if data.get('clear_auth'):
        if supplied_user not in (None, '') or supplied_pass not in (None, ''):
            return 'Uncheck Clear auth before entering new SMTP credentials.'
        return None

    existing_config = existing_config or {}
    effective_user = supplied_user or existing_config.get('smtp_user') or existing_config.get('MAIL_USERNAME')
    effective_pass = supplied_pass or existing_config.get('smtp_pass') or existing_config.get('MAIL_PASSWORD')
    if bool(effective_user) != bool(effective_pass):
        return 'Provide both SMTP username and password, or leave both blank.'
    return None


@notifications_api.route('/admin/email-provider', methods=['GET'])
@login_required
@require_role('owner', 'super_admin')
def get_email_provider_settings():
    """Read Owner-managed SMTP settings without returning stored credentials."""
    setting = CommunicationSettingsService.get_email_setting()
    if setting:
        try:
            config = CommunicationSettingsService._decrypt_config(setting.config or {})
            from app.utils.crypto import is_encrypted_json
            if config and not is_encrypted_json(setting.config):
                setting.config = CommunicationSettingsService._encrypt_config(config)
                db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.error(
                "Email provider settings could not be decrypted (exception_type=%s)",
                type(exc).__name__,
            )
            return jsonify({'error': 'Stored email settings could not be decrypted'}), 503
        return jsonify({
            'source': 'database',
            'enabled': bool(setting.enabled),
            'provider': setting.provider or 'smtp',
            'smtp_host': config.get('smtp_host', ''),
            'smtp_port': config.get('smtp_port', 587),
            'use_tls': bool(config.get('use_tls', True)),
            'use_ssl': bool(config.get('use_ssl', False)),
            'default_sender': config.get('default_sender', ''),
            'smtp_user_configured': bool(config.get('smtp_user')),
            'smtp_password_configured': bool(config.get('smtp_pass')),
        })

    # Environment fallback is read-only and remains active only until the Owner
    # saves a database provider record. Never return username/password values.
    cfg = current_app.config
    return jsonify({
        'source': 'environment',
        'enabled': bool(cfg.get('MAIL_SERVER')),
        'provider': 'smtp',
        'smtp_host': cfg.get('MAIL_SERVER') or '',
        'smtp_port': cfg.get('MAIL_PORT', 587),
        'use_tls': bool(cfg.get('MAIL_USE_TLS', True)),
        'use_ssl': bool(cfg.get('MAIL_USE_SSL', False)),
        'default_sender': cfg.get('MAIL_DEFAULT_SENDER') or '',
        'smtp_user_configured': bool(cfg.get('MAIL_USERNAME')),
        'smtp_password_configured': bool(cfg.get('MAIL_PASSWORD')),
    })


@notifications_api.route('/admin/email-provider', methods=['PUT'])
@login_required
@require_role('owner', 'super_admin')
def save_email_provider_settings():
    """Save the canonical shared SMTP provider; secret fields are write-only."""
    data = request.get_json(silent=True) or {}
    provider = str(data.get('provider', 'smtp')).strip().lower()
    host = str(data.get('smtp_host') or '').strip()
    sender = str(data.get('default_sender') or '').strip()
    try:
        port = int(data.get('smtp_port', 587))
    except (TypeError, ValueError):
        return jsonify({'error': 'SMTP port must be an integer'}), 400
    use_tls = bool(data.get('use_tls', True))
    use_ssl = bool(data.get('use_ssl', False))
    if provider != 'smtp':
        return jsonify({'error': 'Only SMTP is enabled for the shared mail transport'}), 400
    if not 1 <= port <= 65535:
        return jsonify({'error': 'SMTP port must be between 1 and 65535'}), 400
    if use_tls and use_ssl:
        return jsonify({'error': 'Choose STARTTLS or SSL, not both'}), 400

    existing_setting = CommunicationSettingsService.get_email_setting()
    if 'enabled' in data:
        enabled = bool(data.get('enabled'))
    elif existing_setting is not None:
        enabled = bool(existing_setting.enabled)
    else:
        enabled = True
    if enabled and (not host or not sender or '@' not in sender):
        return jsonify({'error': 'SMTP host and a valid default sender are required'}), 400

    missing_environment_credentials = _missing_initial_smtp_credentials(
        data,
        current_app.config,
        existing_setting,
    )
    if missing_environment_credentials:
        fields = ' and '.join(missing_environment_credentials)
        return jsonify({
            'error': (
                'This is the first Owner-managed SMTP save. Re-enter the configured '
                f'{fields} in the write-only fields before saving. Blank values would '
                'otherwise stop using the environment credentials. No settings were changed.'
            )
        }), 409

    existing_config = {}
    if existing_setting is not None and not data.get('clear_auth'):
        try:
            existing_config = CommunicationSettingsService._decrypt_config(
                existing_setting.config or {}
            )
        except Exception as exc:
            db.session.rollback()
            logger.error(
                "Existing SMTP settings could not be decrypted (exception_type=%s)",
                type(exc).__name__,
            )
            return jsonify({'error': 'Stored email settings could not be decrypted'}), 503

    auth_pair_error = _smtp_auth_pair_error(data, existing_config)
    if auth_pair_error:
        return jsonify({'error': auth_pair_error}), 400

    config = {
        'smtp_host': host,
        'smtp_port': port,
        'smtp_user': data.get('smtp_user'),
        'smtp_pass': data.get('smtp_pass'),
        'use_tls': use_tls,
        'use_ssl': use_ssl,
        'default_sender': sender,
    }
    clear_keys = ['smtp_user', 'smtp_pass'] if data.get('clear_auth') else []
    register_secret_mapping(config)
    try:
        setting = CommunicationSettingsService.upsert_setting(
            key='email_provider',
            channel='email',
            provider='smtp',
            enabled=enabled,
            config=config,
            description='Shared Owner-managed SMTP configuration for web and Celery',
            updated_by=current_user.id,
            clear_secret_keys=clear_keys,
        )
    except Exception as exc:
        db.session.rollback()
        logger.error(
            "Owner SMTP settings save failed (exception_type=%s)",
            type(exc).__name__,
        )
        return jsonify({'error': 'SMTP settings could not be encrypted and saved'}), 503

    return jsonify({
        'success': True,
        'message': 'SMTP settings saved securely',
        'setting': _serialize_comm_setting(setting),
    })


@notifications_api.route('/admin/email-provider/test', methods=['POST'])
@login_required
@require_role('owner', 'super_admin')
def queue_email_provider_test():
    """Queue a real email through the same Celery worker delivery path."""
    from app.notifications.tasks import send_email_test_task
    from app.utils.security import validate_email

    data = request.get_json(silent=True) or {}
    recipient = str(data.get('recipient') or '').strip()
    if not validate_email(recipient):
        return jsonify({'error': 'Enter a valid test recipient address'}), 400
    try:
        queued = send_email_test_task.apply_async(
            kwargs={'recipient': recipient, 'requested_by_user_id': current_user.id}
        )
    except Exception as exc:
        logger.error(
            "Could not queue SMTP delivery test (exception_type=%s)",
            type(exc).__name__,
        )
        return jsonify({'error': 'The asynchronous email test could not be queued'}), 503
    return jsonify({
        'success': True,
        'task_id': queued.id,
        'status': 'queued',
        'message': 'Email test queued for the Celery worker',
    }), 202


@notifications_api.route('/admin/email-provider/test/<task_id>', methods=['GET'])
@login_required
@require_role('owner', 'super_admin')
def email_provider_test_status(task_id):
    """Read only the safe result fields of an asynchronous test task."""
    from app.notifications.tasks import send_email_test_task
    try:
        result = send_email_test_task.AsyncResult(task_id)
        payload = {'task_id': task_id, 'state': result.state}
        if result.successful() and isinstance(result.result, dict):
            payload.update({
                'delivery_status': result.result.get('status'),
                'error_code': result.result.get('error_code'),
            })
        elif result.failed():
            payload['delivery_status'] = 'failed'
            payload['error_code'] = type(result.result).__name__
        return jsonify(payload)
    except Exception as exc:
        logger.error(
            "Could not read SMTP test task status (exception_type=%s)",
            type(exc).__name__,
        )
        return jsonify({'error': 'Test status is temporarily unavailable'}), 503


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
    try:
        config = CommunicationSettingsService._decrypt_config(s.config or {})
    except Exception:
        # Never return encrypted blobs or raw configuration after a decrypt error.
        config = {}
    return {
        'id': s.id,
        'key': s.key,
        'channel': s.channel,
        'provider': s.provider,
        'enabled': s.enabled,
        'description': s.description,
        'config': _redact_config(config),
        'updated_at': s.updated_at.isoformat() if s.updated_at else None,
    }


def _serialize_aggregator(a: NotificationAggregator) -> Dict[str, Any]:
    try:
        credentials = CommunicationSettingsService._decrypt_config(a.credentials or {})
    except Exception:
        credentials = {}
    webhook_url = credentials.get('webhook_url') or a.webhook_url
    return {
        'id': a.id,
        'name': a.name,
        'provider_type': a.provider_type,
        'channels': a.channels,
        'enabled': a.enabled,
        'webhook_url': '***REDACTED***' if webhook_url else None,
        'webhook_url_configured': bool(webhook_url),
        'priority': a.priority,
        'credentials': _redact_config(credentials),
        'updated_at': a.updated_at.isoformat() if a.updated_at else None,
    }


def _redact_config(cfg: Any) -> Any:
    """Recursively redact secret values before any API serialization."""
    if isinstance(cfg, dict):
        redacted = {}
        for key, value in cfg.items():
            if is_secret_config_key(key):
                redacted[key] = '***REDACTED***' if value not in (None, '') else ''
            else:
                redacted[key] = _redact_config(value)
        return redacted
    if isinstance(cfg, list):
        return [_redact_config(value) for value in cfg]
    if isinstance(cfg, tuple):
        return [_redact_config(value) for value in cfg]
    return cfg


def is_secret_config_key(key: object) -> bool:
    from app.utils.log_redaction import is_sensitive_name
    return is_sensitive_name(key)


def _celery_available() -> bool:
    try:
        from app.celery_app import celery_app
        return celery_app is not None
    except Exception:
        return False
