"""
Production Console SocketIO Namespace.

Provides real-time log streaming to authorized Owner/Super Admin users.
Includes connection authorization and event filtering.
"""
import logging
from flask_socketio import Namespace, emit, disconnect
from flask_login import current_user
from flask import has_request_context, request

from app.admin.owner.decorators import owner_or_superadmin_required
from app.extensions import db
from app.identity.models.user import User
from app.production_console.streaming import ProductionConsoleHandler

logger = logging.getLogger(__name__)


class ProductionConsoleNamespace(Namespace):
    """SocketIO namespace for production console real-time streaming."""
    
    def on_connect(self, auth=None):
        """Handle client connection - verify authorization."""
        if not has_request_context():
            logger.warning("Console connection rejected: no request context")
            return False
        
        # Check authentication
        if not current_user or not current_user.is_authenticated:
            logger.warning("Console connection rejected: not authenticated")
            return False
        
        # Check authorization - must be owner or super_admin
        try:
            # Ensure user is attached to session
            if current_user not in db.session:
                db.session.merge(current_user, load=False)
            
            from app.auth.helpers import has_global_role
            is_owner = has_global_role(current_user, 'owner')  # type: ignore[arg-type]
            is_super = has_global_role(current_user, 'super_admin')  # type: ignore[arg-type]
            
            if not (is_owner or is_super):
                logger.warning(f"Console connection rejected: user {current_user.id} not authorized")
                return False
            
        except Exception as e:
            logger.error(f"Console authorization error: {e}")
            return False
        
        # Connection authorized
        logger.info(f"Production console connected: user={current_user.id}, role={'owner' if is_owner else 'super_admin'}")
        
        # Send initial connection confirmation
        emit('connected', {
            'status': 'connected',
            'message': 'Production console connected',
            'user': current_user.username,
            'role': 'owner' if is_owner else 'super_admin',
        })
        
        # Send recent history
        history = ProductionConsoleHandler.get_recent_history(limit=500)
        if history:
            emit('history', {'events': history})
        
        return True
    
    def on_disconnect(self):
        """Handle client disconnection."""
        if current_user and current_user.is_authenticated:
            logger.info(f"Production console disconnected: user={current_user.id}")
        else:
            logger.info("Production console disconnected: unauthenticated")
    
    def on_request_history(self, data=None):
        """Handle request for recent history."""
        if not current_user or not current_user.is_authenticated:
            return
        
        limit = 500
        if data and isinstance(data, dict):
            limit = min(data.get('limit', 500), 2000)
        
        history = ProductionConsoleHandler.get_recent_history(limit=limit)
        emit('history', {'events': history})
    
    def on_clear_history(self, data=None):
        """Handle clear history request."""
        if not current_user or not current_user.is_authenticated:
            return
        
        try:
            from app.auth.helpers import has_global_role
            is_owner = has_global_role(current_user, 'owner')  # type: ignore[arg-type]
            if not is_owner:
                emit('error', {'message': 'Only owner can clear history'})
                return
            
            success = ProductionConsoleHandler.clear_history()
            if success:
                emit('history_cleared', {'status': 'success'})
                logger.info(f"Production console history cleared by owner: {current_user.id}")
            else:
                emit('error', {'message': 'Failed to clear history'})
        except Exception as e:
            logger.error(f"Clear history error: {e}")
            emit('error', {'message': 'Failed to clear history'})
    
    def on_filter_change(self, data=None):
        """Handle filter change - client-side filtering, just acknowledge."""
        if not current_user or not current_user.is_authenticated:
            return
        
        # Server doesn't need to do anything for filtering - client handles it
        # But we can log the filter change for audit
        if data:
            logger.debug(f"Console filter changed by {current_user.id}: {data}")
    
    def on_ping(self, data=None):
        """Handle ping for connection health check."""
        emit('pong', {'timestamp': data.get('timestamp') if data else None})


def register_production_console_namespace(socketio_instance):
    """Register the production console namespace with SocketIO."""
    socketio_instance.on_namespace(ProductionConsoleNamespace('/console'))
    logger.info("Production console SocketIO namespace registered")