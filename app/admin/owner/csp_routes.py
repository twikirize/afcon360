"""CSP Settings Routes - Toggle upgrade-insecure-requests"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.admin.owner.models import SystemSetting
from app.admin.owner.decorators import owner_required

csp_bp = Blueprint('csp', __name__, url_prefix='/owner/csp')


@csp_bp.route('/status', methods=['GET'])
@login_required
@owner_required
def get_status():
    """Get current CSP upgrade-insecure-requests status"""
    setting = SystemSetting.query.filter_by(key='CSP_UPGRADE_INSECURE').first()
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

    setting = SystemSetting.query.filter_by(key='CSP_UPGRADE_INSECURE').first()
    if not setting:
        setting = SystemSetting(
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