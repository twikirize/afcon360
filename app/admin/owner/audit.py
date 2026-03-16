# app/admin/owner/audit.py
"""
Decorator-based audit logging for owner routes
"""
from functools import wraps
from flask import request, g
from flask_login import current_user  # 🔴 FIXED: Import from flask_login, not flask
from app.extensions import db
from app.admin.owner.models import OwnerAuditLog
from app.admin.owner.utils import log_owner_action


def audit_owner_action(action, category=None, capture_response=False):
    """
    Decorator to automatically log owner actions with rich context

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
            # Capture request details before execution
            request_details = {
                'method': request.method,
                'path': request.path,
                'args': str(request.args),
                'form_keys': list(request.form.keys()) if request.form else [],
                'endpoint': request.endpoint
            }

            # Execute the function
            try:
                result = f(*args, **kwargs)

                # Log success
                details = {
                    'request': request_details,
                    'response_status': 'success'
                }

                if capture_response:
                    # Be careful not to log sensitive data
                    details['response'] = str(result)[:500]

                log_owner_action(
                    action=action,
                    category=category or 'route_action',
                    details=details,
                    status='success'
                )

                return result

            except Exception as e:
                # Log failure
                log_owner_action(
                    action=action,
                    category=category or 'route_action',
                    details={
                        'request': request_details,
                        'error': str(e),
                        'error_type': type(e).__name__
                    },
                    status='failure',
                    failure_reason=str(e)
                )
                # Re-raise the exception
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