"""Centralized error handling - logs to audit system, never exposes to users"""
import logging
from functools import wraps
from flask import flash, current_app, request
from app.audit.models import AuditLog
from app.extensions import db

logger = logging.getLogger(__name__)

def log_error_to_audit(user_id, error_type, error_message, context=None):
    """Log error to audit system instead of showing to user"""
    try:
        # Don't use request.path as resource_id since it's not a UUID
        # Instead, use None for resource_id to avoid IDGuard violations
        AuditLog.log(
            user_id=user_id,
            action="SYSTEM_ERROR",
            resource_type="system",
            resource_id=None,  # Not a specific entity, so pass None
            ip_address=request.remote_addr if request else None,
            user_agent=request.user_agent.string if request and request.user_agent else None,
            meta={
                "error_type": error_type,
                "error_message": str(error_message),
                "context": context or {},
                "url": request.url if request else None,
                "method": request.method if request else None,
                "path": request.path if request else None  # Store path in meta instead
            },
            db_session=db.session
        )
        db.session.commit()
    except Exception as log_error:
        logger.error(f"Failed to log error to audit: {log_error}")

def safe_flash(message, category="info"):
    """Safe flash that never shows error details to users"""
    # Don't flash if it's an error message with technical details
    if category == "danger" and ("Error loading" in message or "Could not build url" in message):
        # Log instead
        logger.warning(f"Suppressed error flash: {message}")
        return
    flash(message, category)

def handle_url_error(endpoint):
    """Handle URL building errors gracefully"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                if "Could not build url" in str(e):
                    # Log to audit
                    from flask_login import current_user
                    user_id = current_user.id if current_user.is_authenticated else None
                    log_error_to_audit(
                        user_id=user_id,
                        error_type="URLBuildError",
                        error_message=str(e),
                        context={"endpoint": endpoint}
                    )
                    # Return safe fallback
                    return '#'
                raise
        return wrapper
    return decorator
