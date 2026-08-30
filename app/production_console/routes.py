"""
Production Console Blueprint.

Provides the secure web interface for Owner/Super Admin to view live production logs.
"""
import os
from datetime import datetime, timezone
from flask import Blueprint, render_template, current_app, jsonify, request
from flask_login import login_required, current_user

from app.admin.owner.decorators import owner_or_superadmin_required
from app.production_console.streaming import ProductionConsoleHandler, FrontendEventCapture
from app.admin.owner.utils import get_system_health
from app.extensions import csrf

production_console_bp = Blueprint('production_console', __name__, url_prefix='/admin/owner')


@production_console_bp.route('/production-console')
@login_required
@owner_or_superadmin_required
def production_console():
    """
    Production Console - Live terminal-style log viewer for Owner/Super Admin.
    
    Shows real-time application logs, errors, HTTP requests, database events,
    Celery tasks, and security events with full traceback details.
    """
    app_env = os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "local"
    flask_env = os.getenv("FLASK_ENV", "production")
    
    try:
        async_mode = current_app.extensions.get('socketio', None)
        async_mode = async_mode.async_mode if async_mode else "unknown"
    except Exception:
        async_mode = "unknown"
    
    # Get initial history for page load
    try:
        initial_history = ProductionConsoleHandler.get_recent_history(limit=200)
    except Exception as e:
        current_app.logger.error(f"Failed to get console history: {e}")
        initial_history = []
    
    # Get system health for status bar
    try:
        health = get_system_health()
    except Exception as e:
        current_app.logger.error(f"Failed to get system health: {e}")
        health = {
            'database': {'status': 'unknown', 'latency': 0},
            'redis': {'status': 'unknown', 'latency': 0},
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    return render_template(
        'owner/production_console.html',
        app_env=app_env,
        flask_env=flask_env,
        async_mode=async_mode,
        initial_history=initial_history,
        health=health,
    )


@production_console_bp.route('/production-console/history')
@login_required
@owner_or_superadmin_required
def console_history():
    """API endpoint to fetch recent console history."""
    try:
        limit = min(request.args.get('limit', 500, type=int), 2000)
        history = ProductionConsoleHandler.get_recent_history(limit=limit)
        return jsonify({'events': history, 'count': len(history)})
    except Exception as e:
        current_app.logger.error(f"Console history API error: {e}")
        return jsonify({'error': 'Failed to fetch history'}), 500


@production_console_bp.route('/production-console/health')
@login_required
@owner_or_superadmin_required
def console_health():
    """API endpoint for system health status."""
    try:
        health = get_system_health()
        return jsonify(health)
    except Exception as e:
        current_app.logger.error(f"Console health API error: {e}")
        return jsonify({'error': 'Failed to fetch health'}), 500


@production_console_bp.route('/production-console/clear', methods=['POST'])
@login_required
@owner_or_superadmin_required
@csrf.exempt
def console_clear():
    """Clear console history (owner only)."""
    try:
        from app.auth.helpers import has_global_role
        if not has_global_role(current_user, 'owner'):  # type: ignore[arg-type]
            return jsonify({'error': 'Only owner can clear history'}), 403
        
        success = ProductionConsoleHandler.clear_history()
        if success:
            return jsonify({'status': 'success'})
        return jsonify({'error': 'Failed to clear history'}), 500
    except Exception as e:
        current_app.logger.error(f"Console clear error: {e}")
        return jsonify({'error': 'Failed to clear history'}), 500


@production_console_bp.route('/production-console/frontend-event', methods=['POST'])
@login_required
@csrf.exempt
def frontend_event():
    """Receive frontend events (clicks, navigation, performance, errors)."""
    try:
        data = request.get_json(silent=True) or {}
        message = (data.get('message') or '').strip()
        if not message:
            return jsonify({'error': 'message required'}), 400
        
        FrontendEventCapture.capture(data)
        return jsonify({'status': 'ok'})
    except Exception as e:
        current_app.logger.error(f"Frontend event error: {e}")
        return jsonify({'error': 'Failed to record event'}), 500