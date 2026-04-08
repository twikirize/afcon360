# app/admin/owner/utils.py - Fix the log_owner_action function
"""
Owner utilities - Core audit logging and system health functions
FIXED: Now uses internal BIGINT ID (user.id) for database relations
"""

import logging
import json
import time
from datetime import datetime

from flask import request, g
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
    owner_id: int = None  # Use BIGINT ID
) -> bool:
    """
    Core audit logging function - logs actions performed by owners.
    FIXED: Uses internal BIGINT ID (user.id) instead of UUID string.
    """
    try:
        # CRITICAL: Rollback any aborted transaction before proceeding
        try:
            db.session.rollback()
        except Exception:
            pass

        # Determine internal owner ID and log source
        final_owner_id = None

        if owner_id is not None:
            # Trusted system action - owner_id should be the BIGINT
            final_owner_id = owner_id
            log_source = "system"
        elif current_user and current_user.is_authenticated:
            # Use the internal BIGINT id, NOT the UUID user_id
            try:
                final_owner_id = current_user.id # Changed from current_user.get_id()
                log_source = "owner"
            except Exception as e:
                logger.warning(f"Could not resolve current_user for audit log: action={action}, error={e}")
                return False
        else:
            logger.debug(f"No authenticated user for audit log: action={action}")
            return False

        # Extra safety check: ensure we're not trying to insert a UUID into a BIGINT column
        if isinstance(final_owner_id, str) and '-' in final_owner_id:
            logger.error(f"CRITICAL: Attempted to log action '{action}' with UUID '{final_owner_id}' instead of BIGINT. Blocking insert.")
            return False

        # Prepare enhanced details with metadata
        enhanced_details = {
            **(details or {}),
            '_log_source': log_source,
            '_timestamp': datetime.utcnow().isoformat()
        }

        # Extract request info safely
        ip_address = None
        user_agent = None
        try:
            ip_address = request.remote_addr if request else None
            user_agent = request.user_agent.string if request and hasattr(request, 'user_agent') else None
        except Exception:
            pass

        # Create audit log entry
        audit_log = OwnerAuditLog(
            owner_id=final_owner_id,
            action=action,
            category=category or 'action',
            details=enhanced_details,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            failure_reason=failure_reason
        )

        # db.session.add(audit_log)
        # db.session.commit()()
        logger.debug(f"Audit log created: {action} by owner ID {final_owner_id}")
        return True

    except Exception as e:
        logger.exception(f"Failed to log owner action '{action}': {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return False


def get_system_health() -> dict:
    """
    Get system health metrics including database and Redis connectivity.
    FIXED: Uses raw connection to avoid session issues.
    """
    from app.extensions import redis_client

    health = {
        'database': {'status': 'unknown', 'latency': 0},
        'redis': {'status': 'unknown', 'latency': 0},
        'timestamp': datetime.utcnow().isoformat()
    }

    # Database connectivity check using raw connection (bypasses session)
    try:
        start = time.time()
        with db.engine.connect() as conn:
            conn.execute(text('SELECT 1'))
            conn.commit()  # Explicit commit for raw connection
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
