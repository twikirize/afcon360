"""
TTL-aware key/value store for short-lived auth state (OTPs, pending
registrations, rate-limit counters).

Why this exists
---------------
``app.extensions.cache`` is a *Flask-Caching* ``Cache``. It exposes only
``get``/``set``/``add``/``delete`` and its ``set()`` takes ``timeout=``.
Existing code called ``cache.set(key, value, ex=ttl)`` and ``cache.ttl(key)``,
which are **redis-py** APIs. Those calls raise ``TypeError`` /
``AttributeError`` at runtime, so OTPs were never actually stored and email
verification could never succeed.

This module talks to Redis directly (via ``app.extensions.redis_client``) so we
get the primitives this flow genuinely needs - atomic ``INCR``, ``EXPIRE``,
``TTL`` and ``SET NX`` - and transparently falls back to a thread-safe
in-process store when Redis is unavailable (local dev, unit tests).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class _MemoryStore:
    """Thread-safe in-process fallback with TTL semantics."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, Optional[float]]] = {}
        self._lock = threading.RLock()

    def _expired(self, expires_at: Optional[float]) -> bool:
        return expires_at is not None and time.time() >= expires_at

    def _purge(self) -> None:
        now = time.time()
        dead = [k for k, (_, exp) in self._data.items() if exp is not None and now >= exp]
        for k in dead:
            self._data.pop(k, None)

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if self._expired(expires_at):
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        with self._lock:
            self._purge()
            self._data[key] = (value, time.time() + ttl if ttl else None)
            return True

    def set_if_absent(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        with self._lock:
            if self.get(key) is not None:
                return False
            return self.set(key, value, ttl)

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._data.pop(key, None) is not None

    def incr(self, key: str, ttl: Optional[int] = None) -> int:
        with self._lock:
            current = self.get(key)
            new_value = int(current or 0) + 1
            # Preserve the original window: only set a TTL when creating.
            if current is None:
                self.set(key, new_value, ttl)
            else:
                _, expires_at = self._data[key]
                self._data[key] = (new_value, expires_at)
            return new_value

    def ttl(self, key: str) -> int:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return -2
            _, expires_at = entry
            if expires_at is None:
                return -1
            remaining = int(expires_at - time.time())
            return remaining if remaining > 0 else -2

    def expire(self, key: str, ttl: int) -> bool:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return False
            value, _ = entry
            self._data[key] = (value, time.time() + ttl)
            return True


_memory_store = _MemoryStore()


def _redis():
    """Return a live Redis client, or ``None`` to use the memory fallback."""
    try:
        from app.extensions import redis_client
        client = redis_client.client
        return client
    except Exception as e:
        logger.debug("Redis unavailable, using in-memory auth store: %s", e)
        return None


def _encode(value: Any) -> bytes:
    return json.dumps(value).encode("utf-8")


def _decode(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def store_set(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Store *value* under *key*, expiring after *ttl* seconds."""
    client = _redis()
    if client is not None:
        try:
            return bool(client.set(key, _encode(value), ex=ttl))
        except Exception as e:
            logger.warning("Redis SET failed for %s (%s); falling back to memory", key, e)
    return _memory_store.set(key, value, ttl)


def store_set_if_absent(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Atomically store *value* only when *key* does not already exist."""
    client = _redis()
    if client is not None:
        try:
            return bool(client.set(key, _encode(value), ex=ttl, nx=True))
        except Exception as e:
            logger.warning("Redis SETNX failed for %s (%s); falling back to memory", key, e)
    return _memory_store.set_if_absent(key, value, ttl)


def store_get(key: str) -> Optional[Any]:
    """Return the value stored at *key*, or ``None`` if missing/expired."""
    client = _redis()
    if client is not None:
        try:
            return _decode(client.get(key))
        except Exception as e:
            logger.warning("Redis GET failed for %s (%s); falling back to memory", key, e)
    return _memory_store.get(key)


def store_delete(key: str) -> bool:
    """Delete *key*. Returns True when something was removed."""
    client = _redis()
    if client is not None:
        try:
            return bool(client.delete(key))
        except Exception as e:
            logger.warning("Redis DEL failed for %s (%s); falling back to memory", key, e)
    return _memory_store.delete(key)


def store_incr(key: str, ttl: Optional[int] = None) -> int:
    """
    Atomically increment the counter at *key* and return the new value.

    The TTL is applied only when the counter is first created, so a fixed
    rate-limit window is not extended by subsequent hits.
    """
    client = _redis()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            count, current_ttl = pipe.execute()
            if ttl and current_ttl is not None and current_ttl < 0:
                client.expire(key, ttl)
            return int(count)
        except Exception as e:
            logger.warning("Redis INCR failed for %s (%s); falling back to memory", key, e)
    return _memory_store.incr(key, ttl)


def store_ttl(key: str) -> int:
    """Seconds remaining for *key*: ``-2`` if absent, ``-1`` if no expiry."""
    client = _redis()
    if client is not None:
        try:
            return int(client.ttl(key))
        except Exception as e:
            logger.warning("Redis TTL failed for %s (%s); falling back to memory", key, e)
    return _memory_store.ttl(key)


def store_expire(key: str, ttl: int) -> bool:
    """Reset the expiry of an existing *key* to *ttl* seconds."""
    client = _redis()
    if client is not None:
        try:
            return bool(client.expire(key, ttl))
        except Exception as e:
            logger.warning("Redis EXPIRE failed for %s (%s); falling back to memory", key, e)
    return _memory_store.expire(key, ttl)


def reset_memory_store() -> None:
    """Clear the in-process fallback. Intended for tests only."""
    global _memory_store
    _memory_store = _MemoryStore()
