"""REST API for module toggling with instant effect."""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.services.module_toggle_service import ModuleToggleService
from app.utils.module_guard import module_enabled

module_api_bp = Blueprint('module_api', __name__, url_prefix='/admin/api/modules')

@module_api_bp.route('/toggle', methods=['POST'])
@login_required
def toggle_module():
    """Toggle a module on/off with database persistence."""
    # Check permissions - only owner/super_admin can toggle
    if not (current_user.is_app_owner() or current_user.has_global_role('super_admin')):
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    module = data.get('module', '').strip().lower()
    enabled = data.get('enabled', False)
    
    if not module:
        return jsonify({'error': 'Module name required'}), 400
    
    try:
        # Update database and config
        new_flags = ModuleToggleService.set_flag(module, enabled, updated_by=current_user.id)
        
        return jsonify({
            'success': True,
            'module': module,
            'enabled': enabled,
            'all_flags': new_flags,
            'message': f'{module.title()} module {"enabled" if enabled else "disabled"} successfully'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@module_api_bp.route('/status', methods=['GET'])
@login_required
def get_module_status():
    """Get current status of all modules."""
    modules = ['tourism', 'transport', 'accommodation', 'events', 'wallet']
    return jsonify({
        module: module_enabled(module) for module in modules
    }), 200

@module_api_bp.route('/audit-log', methods=['GET'])
@login_required
def get_audit_log():
    """Get module toggle audit history."""
    if not (current_user.is_app_owner() or current_user.has_global_role('super_admin')):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from app.admin.owner.models import SystemSetting
        history = SystemSetting.get_history('MODULE_FLAGS', limit=50)
        return jsonify({'history': history}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
