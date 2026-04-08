"""
app/wallet/middleware/idempotency.py
Idempotency middleware to prevent duplicate requests.
"""

from functools import wraps
from flask import request, jsonify, current_app
from datetime import datetime, timedelta
import hashlib
import json
from app.extensions import redis_client


class IdempotencyMiddleware:
    """
    Idempotency middleware for POST/PUT/DELETE requests.

    Uses Redis to store processed request responses.
    Returns cached response for duplicate idempotency keys.
    """

    KEY_PREFIX = "idempotency:"
    DEFAULT_TTL_SECONDS = 86400  # 24 hours

    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Initialize middleware with Flask app."""
        self.redis = redis_client
        app.before_request(self._before_request)
        app.after_request(self._after_request)

    def _get_key(self, idempotency_key: str, path: str) -> str:
        """Generate Redis key for idempotency."""
        key_hash = hashlib.sha256(f"{idempotency_key}:{path}".encode()).hexdigest()
        return f"{self.KEY_PREFIX}{key_hash}"

    def _before_request(self):
        """Check for duplicate request before processing."""
        # Only check idempotency for mutating methods
        if request.method not in ['POST', 'PUT', 'PATCH', 'DELETE']:
            return None

        # Get idempotency key from header
        idempotency_key = request.headers.get('X-Idempotency-Key')

        if not idempotency_key:
            # If idempotency is required but not provided
            if current_app.config.get('IDEMPOTENCY', {}).get('require_client_request_id', True):
                return jsonify({
                    "status": "error",
                    "code": "IDEMPOTENCY_KEY_REQUIRED",
                    "message": "X-Idempotency-Key header is required for this request"
                }), 400
            return None

        # Check if already processed
        cache_key = self._get_key(idempotency_key, request.path)

        try:
            cached_response = self.redis.get(cache_key)
            if cached_response:
                # Return cached response
                import pickle
                response_data = pickle.loads(cached_response)
                return jsonify(response_data), 200
        except Exception as e:
            current_app.logger.warning(f"Idempotency cache error: {e}")

        # Store the idempotency key in request context for after_request
        request.idempotency_key = idempotency_key
        request.idempotency_cache_key = cache_key

        return None

    def _after_request(self, response):
        """Cache successful response for future duplicate requests."""
        # Only cache successful responses for mutating methods
        if request.method not in ['POST', 'PUT', 'PATCH', 'DELETE']:
            return response

        if not hasattr(request, 'idempotency_key'):
            return response

        # Only cache successful responses (2xx)
        if 200 <= response.status_code < 300:
            try:
                # Store response data
                response_data = response.get_json()
                if response_data:
                    import pickle
                    ttl = current_app.config.get('IDEMPOTENCY', {}).get('ttl_seconds', self.DEFAULT_TTL_SECONDS)
                    self.redis.setex(
                        request.idempotency_cache_key,
                        ttl,
                        pickle.dumps(response_data)
                    )
            except Exception as e:
                current_app.logger.warning(f"Idempotency cache store error: {e}")

        return response


# Create singleton instance
idempotency = IdempotencyMiddleware()
