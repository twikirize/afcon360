"""REST API for module toggling with instant effect."""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.utils.module_toggle_service import ModuleToggleService
from app.utils.module_guard import module_enabled

module_api_bp = Blueprint('module_api', __name__, url_prefix='/admin/api/modules')

@module_api_bp.route('/toggle', methods=['POST'])
@login_required
def toggle_module():
    """Toggle a module on/off with database persistence."""
    # Check permissions - only owner/super_admin can toggle
    from app.auth.helpers import is_owner, is_system_admin
    
    if not (is_owner(current_user) or is_system_admin(current_user)):
        return jsonify({'error': 'Unauthorized. Requires Owner or Super Admin role.'}), 403
    
    data = request.get_json()
    module = data.get('module', '').strip().lower()
    enabled = data.get('enabled', False)
    
    if not module:
        return jsonify({'error': 'Module name required'}), 400
    
    try:
        from app.extensions import db
        from app.audit.models import AuditLog
        
        # Service handles validation and DB update
        new_flags = ModuleToggleService.set_flag(module, enabled, updated_by=current_user.id)
        
        # Logging is secondary to toggle correctness
        try:
            AuditLog.log(
                user_id=current_user.id,
                action="MODULE_TOGGLE",
                resource_type="system_module",
                resource_id=module,
                meta={"module": module, "enabled": enabled},
                db_session=db.session
            )
            db.session.commit()
        except Exception as log_err:
            db.session.rollback()
            logger.error(f"Audit logging failed: {log_err}")
        
        return jsonify({
            'success': True,
            'module': module,
            'enabled': enabled,
            'all_flags': new_flags,
            'message': f'{module.title()} module {"enabled" if enabled else "disabled"} successfully'
        }), 200
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
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
        from app.models.system_config import SystemConfig
        history = SystemConfig.get_history('MODULE_FLAGS', limit=50)
        return jsonify({'history': history}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
