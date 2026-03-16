# app/admin/owner/utils.py
"""
Owner utilities - Core audit logging and system health functions
"""

import logging
import json
import time
from datetime import datetime

from flask import request
from flask_login import current_user
from sqlalchemy import text

from app.extensions import db
from app.admin.owner.models import OwnerAuditLog

logger = logging.getLogger(__name__)


def log_owner_action(
    action: str,
    category: str = None,
    details: dict = None,
    status: str = 'success',
    failure_reason: str = None,
    user_id: int = None
) -> bool:
    """
    Core audit logging function - logs actions performed by owners.

    Args:
        action: The action being performed (e.g., 'viewed_dashboard')
        category: Category of action (navigation, security, settings, etc.)
        details: Additional context about the action (dict)
        status: success/failure/pending
        failure_reason: If status is failure, explain why
        user_id: Optional explicit user ID (for system actions)

    Returns:
        bool: True if log was created successfully, False otherwise
    """
    try:
        # Determine owner ID and log source
        owner_id = None

        if user_id is not None:
            # Trusted system action
            owner_id = user_id
            log_source = "system"
        elif getattr(current_user, 'is_authenticated', False):
            is_owner = getattr(current_user, 'is_app_owner', lambda: False)()
            if is_owner:
                owner_id = current_user.id
                log_source = "owner"
            else:
                logger.warning(
                    f"Non-owner attempted to create audit log: user={current_user.id}, action={action}"
                )
                return False
        else:
            logger.error(f"Attempted owner log with no authenticated user: action={action}")
            return False

        # Prepare enhanced details with metadata
        enhanced_details = {
            **(details or {}),
            '_log_source': log_source,
            '_timestamp': datetime.utcnow().isoformat()
        }

        # Ensure details are serialized as JSON string
        details_json = json.dumps(enhanced_details)

        # Extract request info safely
        ip_address = getattr(request, 'remote_addr', None)
        user_agent = getattr(getattr(request, 'user_agent', None), 'string', None)

        # Create audit log entry
        audit_log = OwnerAuditLog(
            owner_id=owner_id,
            action=action,
            category=category or 'action',
            details=details_json,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            failure_reason=failure_reason
        )

        db.session.add(audit_log)
        db.session.commit()

        logger.debug(f"Audit log created: {action} by user {owner_id}")
        return True

    except Exception as e:
        logger.exception(f"Failed to log owner action '{action}': {e}")
        db.session.rollback()
        return False


def get_system_health() -> dict:
    """
    Get system health metrics including database and Redis connectivity.

    Returns:
        dict: Health status with latency measurements
    """
    from app.extensions import redis_client

    health = {
        'database': {'status': 'unknown', 'latency': 0},
        'redis': {'status': 'unknown', 'latency': 0},
        'timestamp': datetime.utcnow().isoformat()
    }

    # Database connectivity check
    try:
        start = time.time()
        with db.engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        latency = round((time.time() - start) * 1000, 2)

        health['database'] = {
            'status': 'connected',
            'latency': latency,
            'message': 'Database is responding'
        }
    except Exception as e:
        health['database'] = {
            'status': 'error',
            'latency': 0,
            'message': str(e)
        }
        logger.error(f"Database health check failed: {e}")

    # Redis connectivity check
    try:
        if redis_client:
            start = time.time()
            redis_client.ping()
            latency = round((time.time() - start) * 1000, 2)

            health['redis'] = {
                'status': 'connected',
                'latency': latency,
                'message': 'Redis is responding'
            }
        else:
            health['redis'] = {
                'status': 'not_configured',
                'latency': 0,
                'message': 'Redis client not configured'
            }
    except Exception as e:
        health['redis'] = {
            'status': 'error',
            'latency': 0,
            'message': str(e)
        }
        logger.error(f"Redis health check failed: {e}")

    return health
