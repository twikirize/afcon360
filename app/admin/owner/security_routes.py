"""
Security Routes for Owner Portal
Provides security settings management endpoints and security dashboard
"""
import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, flash, redirect, url_for, render_template, make_response
from flask_login import login_required, current_user
from app.extensions import db
from app.admin.owner.decorators import owner_required
from app.admin.owner.security_service import SecuritySettingsService
from app.models.system_config import SystemConfig as SystemSetting
from app.audit.comprehensive_audit import AuditService, AuditSeverity

logger = logging.getLogger(__name__)

security_bp = Blueprint('owner_security', __name__, url_prefix='/owner/security')


def owner_login_required(f):
    """Decorator that requires both login and owner role"""
    from flask_login import login_required
    return login_required(owner_required(f))


def add_security_routes(owner_bp):
    """Add all security routes to owner blueprint"""

    # ========================================================================
    # API Endpoints (JSON responses)
    # ========================================================================

    @owner_bp.route('/security/lockdown', methods=['POST'])
    @login_required
    def activate_lockdown():
        """Activate emergency lockdown"""
        try:
            if not current_user.is_super_admin():
                return jsonify({'error': 'Unauthorized'}), 403

            success = SecuritySettingsService.activate_lockdown(current_user.id)
            if success:
                AuditService.security(
                    event_type='emergency_lockdown_activated',
                    severity=AuditSeverity.CRITICAL,
                    description='Emergency lockdown activated',
                    user_id=current_user.id,
                    ip_address=request.remote_addr
                )
                return jsonify({'message': 'Lockdown activated successfully'}), 200
            return jsonify({'error': 'Failed to activate lockdown'}), 500
        except Exception as e:
            logger.error(f"Lockdown activation error: {e}")
            return jsonify({'error': 'Internal server error'}), 500

    @owner_bp.route('/security/lockdown', methods=['DELETE'])
    @login_required
    def deactivate_lockdown():
        """Deactivate emergency lockdown"""
        try:
            if not current_user.is_super_admin():
                return jsonify({'error': 'Unauthorized'}), 403

            success = SecuritySettingsService.deactivate_lockdown(current_user.id)
            if success:
                AuditService.security(
                    event_type='emergency_lockdown_deactivated',
                    severity=AuditSeverity.WARNING,
                    description='Emergency lockdown deactivated',
                    user_id=current_user.id,
                    ip_address=request.remote_addr
                )
                return jsonify({'message': 'Lockdown deactivated successfully'}), 200
            return jsonify({'error': 'Failed to deactivate lockdown'}), 500
        except Exception as e:
            logger.error(f"Lockdown deactivation error: {e}")
            return jsonify({'error': 'Internal server error'}), 500

    @owner_bp.route('/security/status', methods=['GET'])
    @login_required
    def get_security_status():
        """Get current security status"""
        try:
            status = SecuritySettingsService.get_security_status()
            return jsonify(status), 200
        except Exception as e:
            logger.error(f"Security status error: {e}")
            return jsonify({'error': 'Internal server error'}), 500

    @owner_bp.route('/security/settings', methods=['GET'])
    @login_required
    def get_security_settings():
        """Get all security settings"""
        try:
            if not current_user.is_super_admin():
                return jsonify({'error': 'Unauthorized'}), 403

            settings = {
                'emergency_lockdown': SecuritySettingsService.get_setting('EMERGENCY_LOCKDOWN', False),
                'maintenance_mode': SecuritySettingsService.get_setting('MAINTENANCE_MODE', False),
                'rate_limit_enabled': SecuritySettingsService.get_setting('RATE_LIMIT_ENABLED', True),
                'audit_logging_enabled': SecuritySettingsService.get_setting('AUDIT_LOGGING_ENABLED', True),
            }
            return jsonify(settings), 200
        except Exception as e:
            logger.error(f"Settings retrieval error: {e}")
            return jsonify({'error': 'Internal server error'}), 500

    # ========================================================================
    # Dashboard Routes (HTML pages)
    # ========================================================================

    @owner_bp.route('/security-dashboard')
    @owner_login_required
    def security_dashboard():
        """Owner security dashboard"""
        settings = SystemSetting.query.order_by(SystemSetting.category).all()
        settings_by_category = {}
        for s in settings:
            settings_by_category.setdefault(s.category, []).append(s)
        return render_template('admin/owner/security_dashboard.html',
                               settings_by_category=settings_by_category)

    @owner_bp.route('/update-setting', methods=['POST'])
    @owner_login_required
    def update_setting():
        """Update a system setting"""
        key = request.form.get('key')
        value = request.form.get('value')
        value_type = request.form.get('value_type', 'str')

        if value_type == 'bool':
            converted = value.lower() in ('true', '1', 'yes', 'on')
        elif value_type == 'int':
            converted = int(value)
        else:
            converted = value

        SystemSetting.set(key=key, value=converted, value_type=value_type, updated_by=current_user.id)
        db.session.commit()

        AuditService.security(
            event_type='setting_updated',
            severity=AuditSeverity.INFO,
            description=f'System setting {key} updated',
            user_id=current_user.id,
            ip_address=request.remote_addr
        )

        flash(f'Setting {key} updated', 'success')
        return redirect(url_for('admin.owner.security_dashboard'))

    @owner_bp.route('/emergency/lockdown', methods=['POST'])
    @owner_login_required
    def emergency_lockdown():
        """Activate emergency lockdown (HTML form version)"""
        SystemSetting.set(key='EMERGENCY_LOCKDOWN', value=True, updated_by=current_user.id)
        db.session.commit()

        AuditService.security(
            event_type='emergency_lockdown_activated',
            severity=AuditSeverity.CRITICAL,
            description='Emergency lockdown activated',
            user_id=current_user.id,
            ip_address=request.remote_addr
        )

        flash('EMERGENCY LOCKDOWN ACTIVATED', 'danger')
        return redirect(url_for('admin.owner.security_dashboard'))

    @owner_bp.route('/emergency/lockdown/disable', methods=['POST'])
    @owner_login_required
    def disable_lockdown():
        """Disable emergency lockdown (HTML form version)"""
        SystemSetting.set(key='EMERGENCY_LOCKDOWN', value=False, updated_by=current_user.id)
        db.session.commit()

        AuditService.security(
            event_type='emergency_lockdown_deactivated',
            severity=AuditSeverity.WARNING,
            description='Emergency lockdown deactivated',
            user_id=current_user.id,
            ip_address=request.remote_addr
        )

        flash('Lockdown disabled', 'success')
        return redirect(url_for('admin.owner.security_dashboard'))

    @owner_bp.route('/toggle-maintenance', methods=['POST'])
    @owner_login_required
    def toggle_maintenance():
        """Toggle maintenance mode"""
        enabled = request.form.get('enabled') == 'true'
        SystemSetting.set(key='MAINTENANCE_MODE', value=enabled, updated_by=current_user.id)
        db.session.commit()
        flash(f'Maintenance mode {"enabled" if enabled else "disabled"}', 'info')
        return redirect(url_for('admin.owner.security_dashboard'))

    @owner_bp.route('/export-settings')
    @owner_login_required
    def export_settings():
        """Export all settings as JSON file download"""
        settings = SystemSetting.query.all()
        data = [{
            'key': s.key,
            'value': s.value,
            'value_type': s.value_type,
            'category': s.category,
            'description': s.description
        } for s in settings]
        response = make_response(jsonify(data))
        response.headers['Content-Disposition'] = 'attachment; filename=settings.json'
        response.headers['Content-Type'] = 'application/json'
        return response

    @owner_bp.route('/import-settings', methods=['POST'])
    @owner_login_required
    def import_settings():
        """Import settings from JSON"""
        if 'settings_file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(url_for('admin.owner.security_dashboard'))

        file = request.files['settings_file']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('admin.owner.security_dashboard'))

        try:
            data = json.load(file)
            for item in data:
                SystemSetting.set(
                    key=item['key'],
                    value=item['value'],
                    value_type=item.get('value_type', 'str'),
                    category=item.get('category', 'general'),
                    description=item.get('description'),
                    updated_by=current_user.id
                )
            db.session.commit()
            flash('Settings imported successfully', 'success')
        except Exception as e:
            flash(f'Error importing settings: {e}', 'danger')

        return redirect(url_for('admin.owner.security_dashboard'))

    # ========================================================================
    # Admin Security Console - User Management
    # ========================================================================

    @owner_bp.route('/admin/users/<int:user_id>/unlock', methods=['POST'])
    @owner_login_required
    def admin_unlock_user(user_id):
        """Unlock a user's account (clear failed logins + lock)."""
        from app.identity.models.user import User
        from app.audit.comprehensive_audit import AuditService, AuditSeverity
        
        target = User.query.get_or_404(user_id)
        if target.is_app_owner() and not current_user.is_app_owner():
            flash('Cannot unlock owner accounts', 'danger')
            return redirect(url_for('admin.owner.security_dashboard'))
        
        old_failed = target.failed_logins
        old_locked = target.locked_until
        
        target.failed_logins = 0
        target.locked_until = None
        db.session.commit()
        
        AuditService.security(
            event_type='account_unlocked',
            severity=AuditSeverity.WARNING,
            description=f'Admin unlocked account for user {target.public_id}',
            user_id=current_user.id,
            ip_address=request.remote_addr,
            extra_data={'target_user_id': target.id, 'old_failed_logins': old_failed, 'old_locked_until': str(old_locked)}
        )
        
        # TODO: Send email notification to user (async)
        flash(f'User {target.username or target.public_id} unlocked successfully', 'success')
        return redirect(url_for('admin.owner.security_dashboard'))

    @owner_bp.route('/admin/users/<int:user_id>/devices')
    @owner_login_required
    def admin_user_devices(user_id):
        """View a user's active device sessions."""
        from app.identity.models.user import User, Session as DeviceSession
        from datetime import datetime, timezone
        
        target = User.query.get_or_404(user_id)
        now = datetime.now(timezone.utc)
        devices = DeviceSession.query.filter_by(user_id=target.id).filter(
            DeviceSession.expires_at > now,
            DeviceSession.revoked_at == None
        ).order_by(DeviceSession.updated_at.desc()).all()
        
        return render_template('admin/owner/user_devices.html',
            target=target, devices=devices, now=now)

    @owner_bp.route('/admin/users/<int:user_id>/devices/revoke-all', methods=['POST'])
    @owner_login_required
    def admin_revoke_all_user_devices(user_id):
        """Force sign-out everywhere for a user."""
        from app.auth.sessions import revoke_all_device_sessions_for_user
        from app.identity.models.user import User
        from app.audit.comprehensive_audit import AuditService, AuditSeverity
        
        target = User.query.get_or_404(user_id)
        if target.is_app_owner() and not current_user.is_app_owner():
            flash('Cannot revoke owner sessions', 'danger')
            return redirect(url_for('admin.owner.security_dashboard'))
        
        count = revoke_all_device_sessions_for_user(target.id, reason='admin_revoked_all')
        
        AuditService.security(
            event_type='all_device_sessions_revoked',
            severity=AuditSeverity.WARNING,
            description=f'Admin revoked all sessions for user {target.public_id}',
            user_id=current_user.id,
            ip_address=request.remote_addr,
            extra_data={'target_user_id': target.id, 'revoked_count': count}
        )
        
        flash(f'Revoked {count} device session(s) for {target.username or target.public_id}', 'success')
        return redirect(url_for('admin.owner.admin_user_devices', user_id=user_id))

    @owner_bp.route('/admin/users/<int:user_id>/security-events')
    @owner_login_required
    def admin_user_security_events(user_id):
        """View a user's security event timeline."""
        from app.identity.models.user import User
        from app.audit.comprehensive_audit import SecurityEventLog
        from sqlalchemy import desc
        
        target = User.query.get_or_404(user_id)
        events = SecurityEventLog.query.filter_by(user_id=target.id).filter(
            SecurityEventLog.event_type.in_([
                'login', 'logout', 'password_change', 'email_change',
                'phone_change', 'mfa_enabled', 'mfa_disabled',
                'device_session_created', 'new_signin',
                'device_session_revoked', 'all_device_sessions_revoked',
                'account_locked', 'account_unlocked',
                'security_answer_verified', 'recovery_code_used'
            ])
        ).order_by(desc(SecurityEventLog.created_at)).limit(100).all()
        
        return render_template('admin/owner/user_security_events.html',
            target=target, events=events)

    @owner_bp.route('/admin/ip-blocks')
    @owner_login_required
    def admin_ip_blocks():
        """View IP block log (from rate limiting / auth failures)."""
        from app.audit.comprehensive_audit import SecurityEventLog
        from sqlalchemy import desc
        
        blocks = SecurityEventLog.query.filter(
            SecurityEventLog.event_type.in_(['ip_blocked', 'rate_limit_exceeded', 'login_ip_blocked'])
        ).order_by(desc(SecurityEventLog.created_at)).limit(200).all()
        
        return render_template('admin/owner/ip_blocks.html', blocks=blocks)

    @owner_bp.route('/admin/ip-blocks/<ip>/clear', methods=['POST'])
    @owner_login_required
    def admin_clear_ip_block(ip):
        """Clear an IP block (Redis + log)."""
        from flask import current_app
        from app.audit.comprehensive_audit import AuditService, AuditSeverity
        import redis
        
        try:
            redis_client = current_app.extensions.get('redis')
            if redis_client:
                redis_client.delete(f'login_ip:{ip}')
                redis_client.delete(f'login_ip:{ip}:locked')
        except Exception:
            pass
        
        AuditService.security(
            event_type='ip_block_cleared',
            severity=AuditSeverity.INFO,
            description=f'Admin cleared IP block for {ip}',
            user_id=current_user.id,
            ip_address=request.remote_addr,
            extra_data={'ip': ip}
        )
        
        flash(f'IP block cleared for {ip}', 'success')
        return redirect(url_for('admin.owner.admin_ip_blocks'))

    return owner_bp
