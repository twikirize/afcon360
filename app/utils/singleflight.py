# app/utils/singleflight.py
"""
Singleflight for hot cache reads.

When many concurrent requests miss the cache for the same key, only ONE
request performs the expensive computation (e.g. availability COUNT queries);
the rest wait for and reuse that single result instead of stampeding the DB.

Uses the existing app.utils.redis_lock redlock implementation so there are no
new dependencies.  If Redis is unavailable the compute runs inline (degraded
but correct).
"""

import json

from app.extensions import redis_client
from app.utils.redis_lock import redis_lock, LockAcquisitionError


def singleflight_json(cache_key, compute_fn, ttl, *, lock_ttl=5, wait_timeout=2):
    """Return JSON-serialisable data, computing it once per cache miss.

    cache_key: Redis key used for both the result cache and the lock.
    compute_fn: callable returning the data (must be JSON-serialisable).
    ttl:       result cache TTL in seconds.
    """
    if redis_client is None:
        return compute_fn()

    cached = redis_client.get(cache_key)
    if cached is not None:
        if isinstance(cached, bytes):
            cached = cached.decode("utf-8")
        return json.loads(cached)

    try:
        with redis_lock(redis_client, f"sf:{cache_key}", timeout=lock_ttl,
                        blocking_timeout=wait_timeout):
            # Re-check: another worker may have filled the cache while we waited.
            cached = redis_client.get(cache_key)
            if cached is not None:
                if isinstance(cached, bytes):
                    cached = cached.decode("utf-8")
                return json.loads(cached)
            data = compute_fn()
            redis_client.setex(cache_key, ttl, json.dumps(data))
            return data
    except LockAcquisitionError:
        # Could not acquire the singleflight lock; compute directly rather
        # than block the request. At most a few duplicate reads under burst.
        return compute_fn()
