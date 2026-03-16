#app/utils/rate_limiting.py
"""
Rate limiting utilities for AFCON360
"""
import time
from functools import wraps
from typing import Optional, Dict, Any
import logging
from flask import request, current_app
from app.utils.exceptions import RateLimitError

logger = logging.getLogger(__name__)

# Simple in-memory rate limiting for development
_rate_limit_store = {}


class RateLimiter:
    """Simple rate limiter implementation"""

    def __init__(
            self,
            max_requests: int = 100,
            window: int = 60,  # seconds
            identifier_func: Optional[callable] = None
    ):
        self.max_requests = max_requests
        self.window = window
        self.identifier_func = identifier_func or self._default_identifier

    def _default_identifier(self):
        """Default identifier using IP address"""
        if request and hasattr(request, 'remote_addr'):
            return f"ip:{request.remote_addr}"
        return "anonymous"

    def _get_key(self, prefix: str = "") -> str:
        """Get rate limit key"""
        identifier = self.identifier_func()
        return f"rate_limit:{prefix}:{identifier}"

    def is_allowed(self, key_prefix: str = "") -> tuple:
        """
        Check if request is allowed
        Returns: (allowed, remaining, reset_time)
        """
        key = self._get_key(key_prefix)
        current_time = time.time()

        # Get or initialize rate limit data
        if key not in _rate_limit_store:
            _rate_limit_store[key] = {
                'count': 1,
                'window_start': current_time
            }
            return True, self.max_requests - 1, current_time + self.window

        data = _rate_limit_store[key]

        # Check if window has expired
        if current_time - data['window_start'] > self.window:
            data['count'] = 1
            data['window_start'] = current_time
            return True, self.max_requests - 1, current_time + self.window

        # Check if limit exceeded
        if data['count'] >= self.max_requests:
            reset_time = data['window_start'] + self.window
            return False, 0, reset_time

        # Increment count and allow
        data['count'] += 1
        remaining = self.max_requests - data['count']
        reset_time = data['window_start'] + self.window

        return True, remaining, reset_time

    def get_headers(self, key_prefix: str = "") -> Dict[str, str]:
        """
        Get rate limit headers
        """
        allowed, remaining, reset_time = self.is_allowed(key_prefix)

        headers = {
            'X-RateLimit-Limit': str(self.max_requests),
            'X-RateLimit-Remaining': str(max(0, remaining)),
            'X-RateLimit-Reset': str(int(reset_time))
        }

        if not allowed:
            headers['Retry-After'] = str(int(reset_time - time.time()))

        return headers


# Update app/utils/rate_limiting.py - change the rate_limit function:

def rate_limit(
        key: str = None,
        limit: int = 100,
        period: int = 60,
        per_method: bool = False,
        per_endpoint: bool = True,
        **kwargs
):
    """
    Rate limiting decorator with flexible parameters.

    Args:
        key: Rate limit key/name
        limit: Maximum requests allowed
        period: Time period in seconds
        per_method: Apply per HTTP method
        per_endpoint: Apply per endpoint
    """
    # Convert to our RateLimiter parameters
    max_requests = limit
    window = period
    key_prefix = key or ""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create rate limiter instance
            limiter = RateLimiter(
                max_requests=max_requests,
                window=window,
                identifier_func=lambda: f"{key_prefix}:{func.__name__}"
            )

            # Check rate limit
            allowed, remaining, reset_time = limiter.is_allowed()

            if not allowed:
                raise RateLimitError(
                    message=f"Rate limit exceeded. Try again in {int(reset_time - time.time())} seconds.",
                    limit=max_requests,
                    window=window
                )

            # Execute function
            response = func(*args, **kwargs)

            # Add rate limit headers if response is a Flask response
            try:
                if hasattr(response, 'headers'):
                    headers = limiter.get_headers()
                    for header_key, header_value in headers.items():
                        response.headers[header_key] = header_value
            except:
                pass

            return response

        return wrapper

    return decorator


def get_rate_limiter(
        max_requests: int = 100,
        window: int = 60,
        identifier_func: Optional[callable] = None
) -> RateLimiter:
    """
    Get a rate limiter instance
    """
    return RateLimiter(max_requests, window, identifier_func)


def clear_rate_limits():
    """Clear all rate limit data (for testing)"""
    _rate_limit_store.clear()
    logger.info("Rate limits cleared")