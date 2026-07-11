"""
Security Routes for Owner Portal
Provides security settings management endpoints and security dashboard
"""
import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, flash, redirect, url_for, render_template
from flask_login import login_required, current_user
from app.extensions import db
from app.admin.owner.decorators import owner_required
from app.admin.owner.security_service import SecuritySettingsService
from app.admin.owner.models import SystemSetting
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
        """Export all settings as JSON"""
        settings = SystemSetting.query.all()
        data = [{
            'key': s.key,
            'value': s.value,
            'value_type': s.value_type,
            'category': s.category,
            'description': s.description
        } for s in settings]
        return jsonify(data)

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

    return owner_bp
