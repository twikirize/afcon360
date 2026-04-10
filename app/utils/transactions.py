import logging
import traceback
from contextlib import contextmanager
from functools import wraps
from typing import Optional
from app.extensions import db

logger = logging.getLogger(__name__)


@contextmanager
def db_transaction(operation_name: str, audit_context: Optional[dict] = None):
    """
    Context manager for database operations.
    - Commits if no errors.
    - Rolls back and logs detailed error + traceback if any exception occurs.
    """
    try:
        # Build audit data properly
        audit_data = {
            'operation': operation_name,
            'status': 'started'
        }
        if audit_context:
            audit_data.update(audit_context or {})

        logger.info(f"🔧 Starting operation: {operation_name}", extra={
            'audit': audit_data
        })
        yield
        db.session.commit()
        logger.info(f"✅ Completed operation: {operation_name}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Failed operation: {operation_name}")
        logger.error(f"Exception Type: {type(e).__name__}")
        logger.error(f"Exception Message: {str(e)}")
        logger.error("Traceback:\n" + traceback.format_exc())
        raise


def transactional(operation_name: str):
    """
    Decorator for wrapping functions in a DB transaction.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with db_transaction(operation_name):
                return func(*args, **kwargs)

        return wrapper

    return decorator
