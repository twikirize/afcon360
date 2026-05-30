"""
app/utils/redis_lock.py
Distributed lock with proper error handling.

Fixed vulnerabilities:
- Raises error if lock.acquire() returns False (no unprotected critical sections)
- Increased timeout to 30s for long-running financial operations
- Graceful handling of expired locks
"""

import redis
from contextlib import contextmanager
from flask import current_app


class LockAcquisitionError(Exception):
    """Raised when lock cannot be acquired."""
    pass


@contextmanager
def redis_lock(client, lock_name, timeout=30, blocking_timeout=5):
    """
    Distributed lock for wallet safety.
    
    Args:
        client: Redis client
        lock_name: Name of the lock
        timeout: Lock timeout in seconds (auto-releases if not released)
        blocking_timeout: How long to wait for acquisition
        
    Raises:
        LockAcquisitionError: If lock cannot be acquired
        
    Yields:
        None (when lock is held)
    """
    lock = client.lock(lock_name, timeout=timeout)
    
    try:
        acquired = lock.acquire(blocking=True, blocking_timeout=blocking_timeout)
        
        if not acquired:
            raise LockAcquisitionError(
                f"Could not acquire lock: {lock_name} "
                f"(timeout={timeout}s, blocking_timeout={blocking_timeout}s)"
            )
        
        # Lock acquired successfully
        yield
        
    finally:
        try:
            # Try to release the lock
            if 'lock' in locals():
                lock.release()
        except Exception:
            # Lock may have expired - that's acceptable
            # The important thing is we don't crash the application
            current_app.logger.warning(f"Lock {lock_name} may have expired before release")
