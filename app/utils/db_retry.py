"""
Database retry decorator for handling deadlocks and transient errors.

P0 Critical: PostgreSQL deadlocks are expected under concurrent load.
This decorator provides automatic retry with exponential backoff.
"""

import time
import logging
from functools import wraps
from typing import Callable, Type, Tuple
from sqlalchemy.exc import OperationalError, DatabaseError, IntegrityError

logger = logging.getLogger(__name__)


class DBRetryError(Exception):
    """Raised when database operation fails after all retries."""
    pass


def retry_on_deadlock(
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    backoff_factor: float = 2.0,
    retry_on: Tuple[Type[Exception], ...] = (OperationalError, DatabaseError, IntegrityError)
) -> Callable:
    """
    Decorator to retry database operations on deadlock/transient errors.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 0.1)
        max_delay: Maximum delay in seconds (default: 2.0)
        backoff_factor: Multiplier for exponential backoff (default: 2.0)
        retry_on: Tuple of exception types to retry on (default: OperationalError, DatabaseError, IntegrityError)
    
    Example:
        @retry_on_deadlock(max_retries=3)
        def transfer_funds():
            # Database operation that might deadlock
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retry_on as e:
                    last_exception = e
                    
                    # Check if it's a deadlock (PostgreSQL error code 40P01)
                    is_deadlock = hasattr(e, 'orig') and hasattr(e.orig, 'pgcode') and e.orig.pgcode == '40P01'
                    
                    # Don't retry if it's the last attempt or not a deadlock
                    if attempt == max_retries:
                        logger.error(
                            f"Database operation failed after {max_retries} retries. "
                            f"Function: {func.__name__}, Error: {str(e)}"
                        )
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    
                    if is_deadlock:
                        logger.warning(
                            f"Deadlock detected in {func.__name__} (attempt {attempt + 1}/{max_retries + 1}). "
                            f"Retrying in {delay:.2f}s..."
                        )
                    else:
                        logger.warning(
                            f"Transient database error in {func.__name__} (attempt {attempt + 1}/{max_retries + 1}). "
                            f"Retrying in {delay:.2f}s... Error: {str(e)}"
                        )
                    
                    time.sleep(delay)
                except Exception as e:
                    # Don't retry on non-database errors
                    logger.error(f"Non-retryable error in {func.__name__}: {str(e)}")
                    raise
            
            # This should never be reached, but just in case
            if last_exception:
                raise DBRetryError(f"Operation failed after {max_retries} retries") from last_exception
        
        return wrapper
    return decorator


def retry_on_specific_error(
    error_message_contains: str,
    max_retries: int = 3,
    delay: float = 0.5
) -> Callable:
    """
    Decorator to retry on specific error messages.
    
    Args:
        error_message_contains: Substring to match in error message
        max_retries: Maximum number of retry attempts
        delay: Delay between retries in seconds
    
    Example:
        @retry_on_specific_error("connection refused", max_retries=5)
        def connect_to_db():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if error_message_contains.lower() in str(e).lower() and attempt < max_retries:
                        logger.warning(
                            f"Error containing '{error_message_contains}' in {func.__name__}. "
                            f"Retrying in {delay}s... (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator
