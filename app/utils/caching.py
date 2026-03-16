#app/utils/caching.py
"""
Caching utilities for AFCON360
"""
import json
import hashlib
import time
from functools import wraps
from typing import Any, Optional, Callable, Union
import logging

logger = logging.getLogger(__name__)

# Simple in-memory cache for development
_cache_store = {}
_cache_locks = {}


def get_cached(key: str, default: Any = None) -> Any:
    """
    Get value from cache
    """
    try:
        item = _cache_store.get(key)
        if item and item.get('expires', 0) > time.time():
            return item['value']
        elif item:
            # Expired, remove it
            del _cache_store[key]
    except Exception as e:
        logger.warning(f"Cache get error for key {key}: {e}")

    return default


def set_cached(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Set value in cache with TTL
    """
    try:
        _cache_store[key] = {
            'value': value,
            'expires': time.time() + ttl
        }
        return True
    except Exception as e:
        logger.error(f"Cache set error for key {key}: {e}")
        return False


def delete_cached(key: str) -> bool:
    """
    Delete value from cache
    """
    try:
        _cache_store.pop(key, None)
        return True
    except Exception as e:
        logger.warning(f"Cache delete error for key {key}: {e}")
        return False


def invalidate_cache_pattern(pattern: str) -> int:
    """
    Invalidate cache keys matching pattern
    Returns number of keys invalidated
    """
    count = 0
    keys_to_delete = []

    for key in _cache_store.keys():
        if pattern in key:
            keys_to_delete.append(key)

    for key in keys_to_delete:
        if delete_cached(key):
            count += 1

    logger.info(f"Invalidated {count} cache keys matching pattern: {pattern}")
    return count


def generate_cache_key(func_name: str, *args, **kwargs) -> str:
    """
    Generate cache key from function name and arguments
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
    return f"cache:{hashlib.md5(key_string.encode()).hexdigest()}"


def cached_query(ttl: int = 300, key_prefix: str = ""):
    """
    Decorator for caching query results
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


def with_cache_lock(timeout: int = 10, raise_on_timeout: bool = False):
    """
    Simple cache lock decorator
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            lock_key = f"lock:{func.__name__}:{hashlib.md5(str(args).encode() + str(kwargs).encode()).hexdigest()}"

            # Simple lock implementation
            lock_acquired = False
            start_time = time.time()

            while not lock_acquired:
                if lock_key not in _cache_locks:
                    _cache_locks[lock_key] = True
                    lock_acquired = True
                elif time.time() - start_time > timeout:
                    if raise_on_timeout:
                        raise TimeoutError(f"Could not acquire lock for {func.__name__}")
                    else:
                        logger.warning(f"Lock timeout for {func.__name__}, proceeding without lock")
                        break
                else:
                    time.sleep(0.1)

            try:
                return func(*args, **kwargs)
            finally:
                if lock_acquired:
                    _cache_locks.pop(lock_key, None)

        return wrapper

    return decorator


def cache_invalidate_on_change(invalidate_patterns: list):
    """
    Decorator to invalidate cache when function modifies data
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
    """Clear all cache"""
    _cache_store.clear()
    logger.info("Cache cleared")