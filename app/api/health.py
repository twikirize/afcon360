"""Health check endpoint for module status monitoring."""
from flask import Blueprint, current_app, jsonify
from flask_login import login_required, current_user
from sqlalchemy import text
from app.extensions import db, limiter, redis_client
from app.utils.module_toggle_service import ModuleToggleService

health_bp = Blueprint('health', __name__, url_prefix='/api/health')


@health_bp.route('/ping', methods=['GET'])
@limiter.exempt
def ping():
    """Public health check — no auth required. Used by Docker and Nginx.

    Explicitly exempt from the global request rate limit so the Docker
    healthcheck (and other authorized internal checks) can poll this endpoint
    indefinitely without exhausting the application-wide quota or being
    converted into a 429/500.
    """
    return jsonify({'status': 'ok'}), 200




@health_bp.route('/ready', methods=['GET'])
@limiter.exempt
def ready():
    """Dependency readiness check, separate from the lightweight liveness ping.

    The response deliberately reports only component state, never connection
    strings or exception details. Redis is required by default outside tests
    and debug mode because it backs production sessions and shared rate limits;
    deployments may explicitly set REDIS_REQUIRED to override that policy.
    """
    database_state = "ok"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        database_state = "unavailable"
        current_app.logger.warning("Readiness check: database unavailable")
        try:
            db.session.rollback()
        except Exception:
            current_app.logger.warning("Readiness check: failed to clear database session")

    try:
        from app import REDIS_AVAILABLE
        if not REDIS_AVAILABLE:
            redis_state = "disabled"
        else:
            redis_client.ping()
            redis_state = "ok"
    except Exception:
        redis_state = "unavailable"
        current_app.logger.warning("Readiness check: shared store unavailable")

    redis_required = current_app.config.get(
        "REDIS_REQUIRED",
        not (current_app.config.get("DEBUG") or current_app.config.get("TESTING")),
    )
    dependencies_ready = (
        database_state == "ok"
        and (redis_state == "ok" or not redis_required)
    )
    # Keep the public response opaque; component details belong in internal
    # server logs, not a publicly enumerable health endpoint.
    response = {"status": "ready" if dependencies_ready else "not_ready"}
    return jsonify(response), (200 if dependencies_ready else 503)


@health_bp.route('/modules', methods=['GET'])
@login_required
def module_health():
    """Get module health status for monitoring."""
    if not (current_user.is_app_owner() or current_user.has_global_role('super_admin')):
        return jsonify({'error': 'Unauthorized'}), 403
    
    modules = ['tourism', 'transport', 'accommodation', 'events', 'wallet', 'geo']
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
