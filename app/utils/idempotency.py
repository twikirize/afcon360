#app/utils/idempotency.py
"""
Idempotency utilities for AFCON360
"""
import hashlib
import json
import time
from functools import wraps
from typing import Optional, Dict, Any, Callable
import logging

logger = logging.getLogger(__name__)

# Store idempotency keys and their results
_idempotency_store = {}


class IdempotencyKey:
    """Idempotency key manager"""

    def __init__(self, key: str, ttl: int = 3600):
        self.key = key
        self.ttl = ttl
        self.created_at = time.time()

    def store_result(self, result: Any, status_code: int = 200):
        """Store operation result"""
        _idempotency_store[self.key] = {
            'result': result,
            'status_code': status_code,
            'created_at': self.created_at,
            'expires_at': self.created_at + self.ttl
        }

    def get_result(self) -> Optional[Dict[str, Any]]:
        """Get stored result if not expired"""
        data = _idempotency_store.get(self.key)

        if not data:
            return None

        # Check if expired
        if time.time() > data['expires_at']:
            del _idempotency_store[self.key]
            return None

        return data

    def exists(self) -> bool:
        """Check if key exists and is not expired"""
        return self.get_result() is not None


def generate_idempotency_key(
        func_name: str,
        args: tuple,
        kwargs: Dict[str, Any],
        request_data: Optional[Dict] = None
) -> str:
    """
    Generate idempotency key from function and arguments
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

    # Add request data if provided
    if request_data:
        try:
            key_parts.append(json.dumps(request_data, sort_keys=True))
        except:
            key_parts.append(repr(request_data))

    key_string = "|".join(key_parts)
    return f"idempotent:{hashlib.sha256(key_string.encode()).hexdigest()}"


def idempotent_request(
        key_getter: Optional[Callable] = None,
        ttl: int = 3600,
        store_errors: bool = False
):
    """
    Decorator for idempotent requests
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get idempotency key
            if key_getter:
                idempotency_key = key_getter(*args, **kwargs)
            else:
                # Try to get from Flask request headers
                try:
                    from flask import request
                    idempotency_key = request.headers.get('Idempotency-Key')
                except:
                    idempotency_key = None

            # If no key provided, just execute normally
            if not idempotency_key:
                return func(*args, **kwargs)

            # Check if we've seen this key before
            key_obj = IdempotencyKey(idempotency_key, ttl)

            if key_obj.exists():
                # Return cached result
                cached_data = key_obj.get_result()
                logger.info(f"Idempotent request - returning cached result for key: {idempotency_key}")

                # For Flask responses, we might need to reconstruct
                if cached_data['status_code'] >= 400 and not store_errors:
                    # Don't return cached errors unless configured to
                    pass
                else:
                    return cached_data['result']

            try:
                # Execute function
                result = func(*args, **kwargs)

                # Store successful result
                status_code = 200
                if hasattr(result, 'status_code'):
                    status_code = result.status_code

                if status_code < 400 or store_errors:
                    key_obj.store_result(result, status_code)

                return result

            except Exception as e:
                logger.error(f"Idempotent request failed for key {idempotency_key}: {e}")

                if store_errors:
                    # Store error result
                    error_result = {
                        'error': str(e),
                        'type': type(e).__name__
                    }
                    key_obj.store_result(error_result, 500)

                raise

        return wrapper

    return decorator


def clear_idempotency_keys():
    """Clear all idempotency keys (for testing)"""
    _idempotency_store.clear()
    logger.info("Idempotency keys cleared")


def cleanup_expired_idempotency_keys():
    """Clean up expired idempotency keys"""
    current_time = time.time()
    expired_keys = []

    for key, data in _idempotency_store.items():
        if current_time > data['expires_at']:
            expired_keys.append(key)

    for key in expired_keys:
        del _idempotency_store[key]

    if expired_keys:
        logger.info(f"Cleaned up {len(expired_keys)} expired idempotency keys")

    return len(expired_keys)