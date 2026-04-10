#app/utils/audit.py
"""
Audit logging utilities for AFCON360
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from flask import request, has_request_context, g
import json
from functools import wraps

logger = logging.getLogger('audit')


class AuditLog:
    """Audit logging class"""

    @staticmethod
    def log(
            action: str,
            user_id: Optional[str] = None,
            details: Optional[Dict[str, Any]] = None,
            resource_type: Optional[str] = None,
            resource_id: Optional[str] = None,
            ip_address: Optional[str] = None,
            user_agent: Optional[str] = None,
            status: str = "success",
            error_message: Optional[str] = None,
            db_session=None  # Add database session parameter for atomicity
    ):
        """
        Log an audit event with optional database transaction integration
        """
        try:
            # Get request context if available
            if has_request_context():
                ip_address = ip_address or request.remote_addr
                user_agent = user_agent or request.user_agent.string
                user_id = user_id or getattr(g, 'user_id', None)

            audit_record = {
                "timestamp": datetime.utcnow().isoformat(),
                "action": action,
                "user_id": user_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "status": status,
                "details": details or {},
                "error_message": error_message
            }

            # Log at INFO level for success, ERROR for failures
            log_level = logging.ERROR if status == "failed" else logging.INFO
            logger.log(log_level, json.dumps(audit_record, default=str))

            # If db_session is provided, also write to database audit table
            if db_session:
                try:
                    from app.audit.models import AuditLog as DBAuditLog
                    db_audit = DBAuditLog(
                        user_id=user_id,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        meta={
                            "ip_address": ip_address,
                            "user_agent": user_agent,
                            "status": status,
                            "details": details or {},
                            "error_message": error_message
                        }
                    )
                    db_session.add(db_audit)
                    # Don't commit here - let the caller handle transaction
                except ImportError:
                    pass  # DBAuditLog model not available
                except Exception as e:
                    logger.error(f"Failed to write to database audit log: {e}")

        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")


def audit_log(
        action: str,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs
):
    """
    Convenience function for audit logging
    """
    AuditLog.log(action, user_id, details, **kwargs)


class AuditContext:
    """Context manager for audit logging"""

    def __init__(
            self,
            action: str,
            resource_type: Optional[str] = None,
            resource_id: Optional[str] = None,
            user_id: Optional[str] = None,
            **kwargs
    ):
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.user_id = user_id
        self.kwargs = kwargs
        self.start_time = datetime.utcnow()
        self.success = True
        self.error = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.success = exc_type is None

        if exc_val:
            self.error = str(exc_val)

        # Calculate duration
        duration = (datetime.utcnow() - self.start_time).total_seconds()

        # Log the audit event
        AuditLog.log(
            action=self.action,
            user_id=self.user_id,
            details={
                "duration": duration,
                "success": self.success,
                **self.kwargs.get('details', {})
            },
            resource_type=self.resource_type,
            resource_id=self.resource_id,
            status="success" if self.success else "failed",
            error_message=self.error
        )

        return False  # Don't suppress exceptions


def with_audit_log(
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        get_resource_id: Optional[callable] = None,
        get_user_id: Optional[callable] = None
):
    """
    Decorator for automatic audit logging
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Determine action name
            audit_action = action or f"{func.__module__}.{func.__name__}"

            # Get resource ID if function provided
            resource_id = None
            if get_resource_id:
                try:
                    resource_id = get_resource_id(*args, **kwargs)
                except:
                    pass

            # Get user ID if function provided
            user_id = None
            if get_user_id:
                try:
                    user_id = get_user_id(*args, **kwargs)
                except:
                    pass

            with AuditContext(
                    action=audit_action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    user_id=user_id,
                    details={
                        "function": func.__name__,
                        "module": func.__module__
                    }
            ):
                return func(*args, **kwargs)

        return wrapper

    return decorator
