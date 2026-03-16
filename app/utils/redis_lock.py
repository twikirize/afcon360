import redis
from contextlib import contextmanager

@contextmanager
def redis_lock(client, lock_name, timeout=10):
    """Distributed lock for wallet safety."""
    lock = client.lock(lock_name, timeout=timeout)
    acquired = lock.acquire(blocking=True)
    try:
        if acquired:
            yield
    finally:
        if acquired:
            lock.release()