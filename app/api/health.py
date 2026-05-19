"""Health check endpoint for module status monitoring."""
from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from app.services.module_toggle_service import ModuleToggleService

health_bp = Blueprint('health', __name__, url_prefix='/api/health')

@health_bp.route('/modules', methods=['GET'])
@login_required
def module_health():
    """Get module health status for monitoring."""
    if not (current_user.is_app_owner() or current_user.has_global_role('super_admin')):
        return jsonify({'error': 'Unauthorized'}), 403
    
    modules = ['tourism', 'transport', 'accommodation', 'events', 'wallet']
    status = {}
    
    for module in modules:
        is_enabled = ModuleToggleService.is_enabled(module)
        status[module] = {
            'enabled': is_enabled,
            'status': 'active' if is_enabled else 'disabled',
            'endpoint': f'/{module}' if is_enabled else None
        }
    
    return jsonify({
        'modules': status,
        'total_modules': len(modules),
        'enabled_count': sum(1 for m in status.values() if m['enabled'])
    }), 200
