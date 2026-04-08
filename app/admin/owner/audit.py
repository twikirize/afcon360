# app/admin/owner/audit.py
"""
Decorator-based audit logging for owner routes
FIXED: Prevents double rollback and handles aborted transactions
"""
import logging
from functools import wraps
from flask import request, g, current_app
from flask_login import current_user
from app.extensions import db
from app.admin.owner.utils import log_owner_action

logger = logging.getLogger(__name__)


def audit_owner_action(action, category=None, capture_response=False):
    """
    Decorator to automatically log owner actions with rich context
    FIXED: Safe transaction handling

    Args:
        action: The action being performed
        category: Category of action
        capture_response: Whether to capture response data (use with caution)

    Usage:
        @audit_owner_action('viewed_dashboard', 'navigation')
        def dashboard():
            ...
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # CRITICAL: Rollback any aborted transaction at start
            try:
                db.session.rollback()
            except Exception:
                pass

            # Capture request details before execution
            request_details = {
                'method': request.method if request else 'unknown',
                'path': request.path if request else 'unknown',
                'endpoint': request.endpoint if request else 'unknown'
            }

            try:
                if request and request.args:
                    request_details['args'] = str(request.args)[:200]
                if request and request.form:
                    request_details['form_keys'] = list(request.form.keys())[:10]
            except Exception:
                pass

            # Execute the function
            try:
                result = f(*args, **kwargs)

                # Log success (don't let audit failure break the response)
                try:
                    log_owner_action(
                        action=action,
                        category=category or 'route_action',
                        details={
                            'request': request_details,
                            'response_status': 'success'
                        },
                        status='success'
                    )
                except Exception as log_err:
                    logger.warning(f"Audit log failed silently for {action}: {log_err}")

                return result

            except Exception as e:
                # Log failure
                try:
                    log_owner_action(
                        action=action,
                        category=category or 'route_action',
                        details={
                            'request': request_details,
                            'error': str(e)[:500],
                            'error_type': type(e).__name__
                        },
                        status='failure',
                        failure_reason=str(e)[:255]
                    )
                except Exception as log_err:
                    logger.warning(f"Audit log failed silently for {action}: {log_err}")

                # Re-raise the original exception
                raise

        return decorated_function

    return decorator


def audit_danger_zone_action(action):
    """
    Special decorator for danger zone actions with extra security logging
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Log entry to danger zone
            log_owner_action(
                action=f"danger_zone_access_{action}",
                category='danger_zone',
                details={'intent': 'entering_danger_zone'}
            )

            # Execute the function
            result = f(*args, **kwargs)

            # Log exit from danger zone
            log_owner_action(
                action=f"danger_zone_executed_{action}",
                category='danger_zone',
                details={'result': 'completed'}
            )

            return result

        return decorated_function

    return decorator


def audit_batch_operation(operations):
    """
    Decorator for batch operations that logs multiple actions

    Args:
        operations: List of dicts with 'action' and 'category' keys
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Log start of batch
            log_owner_action(
                action='batch_operation_started',
                category='batch',
                details={'operations': operations}
            )

            # Execute function
            result = f(*args, **kwargs)

            # Log each operation
            for op in operations:
                log_owner_action(
                    action=op['action'],
                    category=op.get('category', 'batch_operation'),
                    details={'batch_result': str(result)[:200]}
                )

            # Log completion
            log_owner_action(
                action='batch_operation_completed',
                category='batch',
                details={'operations_count': len(operations)}
            )

            return result

        return decorated_function

    return decorator
