import logging
import traceback
from contextlib import contextmanager
from functools import wraps
from app.extensions import db

logger = logging.getLogger(__name__)

@contextmanager
def db_transaction(operation_name: str):
    """
    Context manager for database operations.
    - Commits if no errors.
    - Rolls back and logs detailed error + traceback if any exception occurs.
    """
    try:
        logger.info(f"🔧 Starting operation: {operation_name}")
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
            # If we are already in a transaction context, this will nest,
            # but usually, this is used for top-level service calls.
            with db_transaction(operation_name):
                return func(*args, **kwargs)
        return wrapper
    return decorator
