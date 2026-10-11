"""CSP Settings Routes - Toggle upgrade-insecure-requests + strict enforce flag"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.system_config import SystemConfig
from app.admin.owner.decorators import owner_required
from app.admin.owner.audit import audit_owner_action

csp_bp = Blueprint('csp', __name__, url_prefix='')


@csp_bp.route('/status', methods=['GET'])
@login_required
@owner_required
def get_status():
    """Get current CSP upgrade-insecure-requests status"""
    setting = SystemConfig.query.filter_by(key='CSP_UPGRADE_INSECURE').first()
    return jsonify({
        'enabled': setting and setting.value == 'true',
        'description': setting.description if setting else ''
    })


@csp_bp.route('/toggle', methods=['POST'])
@login_required
@owner_required
def toggle():
    """Toggle CSP upgrade-insecure-requests on/off"""
    data = request.get_json()
    enabled = data.get('enabled', False)

    setting = SystemConfig.query.filter_by(key='CSP_UPGRADE_INSECURE').first()
    if not setting:
        setting = SystemConfig(
            key='CSP_UPGRADE_INSECURE',
            value='false',
            value_type='bool',
            category='security',
            description='Upgrade insecure requests to HTTPS - enable only when SSL is configured'
        )
        db.session.add(setting)

    setting.value = 'true' if enabled else 'false'
    db.session.commit()

    return jsonify({
        'success': True,
        'enabled': enabled,
        'message': f'CSP upgrade-insecure-requests {"enabled" if enabled else "disabled"}'
    })


@csp_bp.route('/strict-status', methods=['GET'])
@login_required
@owner_required
def strict_status():
    """Effective CSP_STRICT_ENFORCE state."""
    from app import is_csp_strict_enforce

    setting = SystemConfig.query.filter_by(key='CSP_STRICT_ENFORCE').first()
    return jsonify({
        'enabled': bool(is_csp_strict_enforce()),
        'stored': bool(setting and setting.value == 'true'),
        'description': setting.description if setting else ''
    })


@csp_bp.route('/strict-toggle', methods=['POST'])
@login_required
@owner_required
@audit_owner_action('toggled_csp_strict_enforce', 'security')
def strict_toggle():
    """Flip CSP_STRICT_ENFORCE. Audited with actor identity; all workers are
    notified over Redis to re-read the flag within seconds."""
    from app import publish_csp_strict_changed, refresh_csp_strict_cache

    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('enabled', False))

    setting = SystemConfig.query.filter_by(key='CSP_STRICT_ENFORCE').first()
    if not setting:
        setting = SystemConfig(
            key='CSP_STRICT_ENFORCE',
            value='false',
            value_type='bool',
            category='security',
            description='Enforce strict CSP (element-level inline requires nonce)'
        )
        db.session.add(setting)

    setting.value = 'true' if enabled else 'false'
    try:
        setting.updated_by = int(current_user.get_id())
    except Exception:
        pass
    db.session.commit()

    # This worker re-reads immediately; the publish covers the other workers.
    refresh_csp_strict_cache()
    publish_csp_strict_changed()

    return jsonify({
        'success': True,
        'enabled': enabled,
        'message': f'CSP strict enforcement {"enabled" if enabled else "disabled"}'
    })
