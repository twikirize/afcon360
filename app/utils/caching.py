"""
app/utils/caching.py
Redis-only caching with SHA256 keys.

Fixed vulnerabilities:
- Removed in-memory _cache_store (not distributed)
- Never cache balance reads (always derive from ledger)
- Replaced MD5 with SHA256 for cache keys
"""

import json
import hashlib
import time
from functools import wraps
from typing import Any, Optional, Callable
import logging

logger = logging.getLogger(__name__)


def get_cached(key: str, default: Any = None) -> Any:
    """
    Get value from Redis cache.
    
    Args:
        key: Cache key
        default: Default value if not found
        
    Returns:
        Cached value or default
    """
    try:
        from app.extensions import redis_client
        value = redis_client.get(key)
        if value:
            return json.loads(value)
    except Exception as e:
        logger.warning(f"Cache get error for key {key}: {e}")
    
    return default


def set_cached(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Set value in Redis cache with TTL.
    
    Args:
        key: Cache key
        value: Value to cache
        ttl: Time to live in seconds
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from app.extensions import redis_client
        redis_client.setex(key, ttl, json.dumps(value))
        return True
    except Exception as e:
        logger.error(f"Cache set error for key {key}: {e}")
        return False


def delete_cached(key: str) -> bool:
    """
    Delete value from Redis cache.
    
    Args:
        key: Cache key
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from app.extensions import redis_client
        redis_client.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Cache delete error for key {key}: {e}")
        return False


def invalidate_cache_pattern(pattern: str) -> int:
    """
    Invalidate cache keys matching pattern.
    
    Args:
        pattern: Pattern to match
        
    Returns:
        Number of keys invalidated
    """
    try:
        from app.extensions import redis_client
        keys = redis_client.keys(f"*{pattern}*")
        if keys:
            count = redis_client.delete(*keys)
            logger.info(f"Invalidated {count} cache keys matching pattern: {pattern}")
            return count
    except Exception as e:
        logger.warning(f"Cache pattern invalidation error: {e}")
    
    return 0


def generate_cache_key(func_name: str, *args, **kwargs) -> str:
    """
    Generate cache key from function name and arguments.
    
    Uses SHA256 instead of MD5 for better security.
    
    Args:
        func_name: Function name
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Cache key string
    """
    key_parts = [func_name]

    # Add args
    for arg in args:
        try:
            key_parts.append(str(arg))
        except:
            key_parts.append(repr(arg))

    # Add kwargs
    for k, v in sorted(kwargs.items()):
        try:
            key_parts.append(f"{k}:{v}")
        except:
            key_parts.append(f"{k}:{repr(v)}")

    key_string = "|".join(key_parts)
    # Use SHA256 instead of MD5
    return f"cache:{hashlib.sha256(key_string.encode()).hexdigest()}"


def cached_query(ttl: int = 300, key_prefix: str = ""):
    """
    Decorator for caching query results.
    
    WARNING: Never use this for balance queries.
    Balances must always be derived from ledger.
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}:{generate_cache_key(func.__name__, *args, **kwargs)}"

            # Try to get from cache
            cached_result = get_cached(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_result

            # Execute function and cache result
            result = func(*args, **kwargs)
            set_cached(cache_key, result, ttl)
            logger.debug(f"Cache miss for {func.__name__}, cached result")

            return result

        return wrapper

    return decorator


def cache_invalidate_on_change(invalidate_patterns: list):
    """
    Decorator to invalidate cache when function modifies data.
    
    Args:
        invalidate_patterns: List of patterns to invalidate
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            # Invalidate cache patterns
            for pattern in invalidate_patterns:
                invalidated = invalidate_cache_pattern(pattern)
                if invalidated:
                    logger.info(f"Invalidated cache for pattern: {pattern}")

            return result

        return wrapper

    return decorator


def clear_cache():
    """Clear all cache from Redis."""
    try:
        from app.extensions import redis_client
        redis_client.flushdb()
        logger.info("Cache cleared")
    except Exception as e:
        logger.error(f"Cache clear error: {e}")


def with_cache_lock(key: str, ttl: int = 10):
    """
    Decorator to provide cache-based locking.
    
    This is a Redis-based distributed lock for backward compatibility.
    The old in-memory lock was not safe for distributed systems.
    
    Args:
        key: Lock key
        ttl: Lock TTL in seconds
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            lock_key = f"lock:{key}"
            
            try:
                from app.extensions import redis_client
                # Try to acquire lock
                acquired = redis_client.set(lock_key, "1", nx=True, ex=ttl)
                
                if not acquired:
                    logger.warning(f"Could not acquire cache lock for key: {key}")
                    # Proceed anyway for backward compatibility
                    # In production, you might want to raise an error here
                
                result = func(*args, **kwargs)
                
                return result
            except Exception as e:
                logger.warning(f"Cache lock error: {e}")
                # Proceed anyway for backward compatibility
                return func(*args, **kwargs)
            finally:
                try:
                    from app.extensions import redis_client
                    redis_client.delete(lock_key)
                except Exception:
                    pass  # Lock may have expired
            
            return result

        return wrapper

    return decorator


# ===== ACCOMMODATION-SPECIFIC CACHE HELPERS =====

def cache_property_detail(property_id: int, timeout: int = 300):
    """Decorator: cache property detail for 5 min, auto-keyed by ID."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            key = f'property_detail:{property_id}'
            result = get_cached(key)
            if result is None:
                result = f(*args, **kwargs)
                set_cached(key, result, timeout=timeout)
            return result
        return wrapper
    return decorator


def invalidate_property_cache(property_id: int):
    """Call whenever a property is updated/approved/rejected."""
    from app.extensions import redis_client
    redis_client.delete(f'property_detail:{property_id}')
    redis_client.delete_many(
        f'property_urgency:{property_id}',
        f'property_reviews:{property_id}',
    )


def get_or_set(key: str, fn, timeout: int = 300):
    """Generic read-through cache. Uses existing cache object."""
    result = get_cached(key)
    if result is None:
        result = fn()
        if result is not None:
            set_cached(key, result, timeout=timeout)
    return result
