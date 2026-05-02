"""
app/wallet/middleware/idempotency.py
Idempotency middleware with JSON serialization and DB persistence.

Fixed vulnerabilities:
- Replaced pickle.loads/dumps with json.loads/dumps (no RCE risk)
- Added PostgreSQL persistence (survives Redis restart)
- Restores original response status code (not hardcoded 200)
"""

import json
import hashlib
from functools import wraps
from flask import request, jsonify, current_app
from datetime import datetime, timedelta
from app.extensions import db, redis_client
from app.wallet.models.audit import IdempotencyKeyModel


class IdempotencyMiddleware:
    """
    Idempotency middleware for POST/PUT/DELETE requests.
    
    Uses Redis for fast lookup with PostgreSQL as source of truth.
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

    def _get_from_db(self, idempotency_key: str) -> dict:
        """
        Get idempotency key from PostgreSQL.
        
        Returns:
            Dict with cached response or None
        """
        try:
            from app.wallet.models.audit import IdempotencyKeyModel
            from sqlalchemy import select
            
            # Check if key exists and not expired
            query = select(IdempotencyKeyModel).where(
                IdempotencyKeyModel.key_value == idempotency_key,
                IdempotencyKeyModel.expires_at > datetime.utcnow()
            )
            
            result = db.session.execute(query).scalar_one_or_none()
            
            if result:
                return {
                    "status": result.response_status,
                    "body": result.response_body
                }
        except Exception as e:
            current_app.logger.warning(f"DB idempotency lookup error: {e}")
        
        return None

    def _save_to_db(
        self,
        idempotency_key: str,
        resource_type: str,
        resource_id: str,
        response_status: int,
        response_body: dict,
        ttl_seconds: int
    ) -> None:
        """
        Save idempotency key to PostgreSQL.
        
        Args:
            idempotency_key: The idempotency key
            resource_type: Type of resource (deposit, withdraw, transfer)
            resource_id: Resource ID (transaction ID)
            response_status: HTTP status code
            response_body: Response body as dict
            ttl_seconds: Time to live in seconds
        """
        try:
            from app.wallet.models.audit import IdempotencyKeyModel
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
            
            # Use ON CONFLICT to handle duplicate keys
            stmt = pg_insert(IdempotencyKeyModel).values(
                key_value=idempotency_key,
                resource_type=resource_type,
                resource_id=resource_id,
                response_status=response_status,
                response_body=response_body,
                expires_at=expires_at,
                created_at=datetime.utcnow(),
                client_ip=self._get_ip_address()
            ).on_conflict_do_nothing(
                index_elements=['key_value']
            )
            
            db.session.execute(stmt)
            db.session.commit()
        except Exception as e:
            current_app.logger.warning(f"DB idempotency save error: {e}")
            db.session.rollback()

    def _get_ip_address(self) -> str:
        """Get client IP address."""
        try:
            return request.remote_addr
        except Exception:
            return None

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

        # Check Redis first (fast path)
        cache_key = self._get_key(idempotency_key, request.path)

        try:
            cached_response = self.redis.get(cache_key)
            if cached_response:
                # Use JSON instead of pickle
                response_data = json.loads(cached_response)
                # Restore original status code
                status_code = response_data.get('status_code', 200)
                body = response_data.get('body', {})
                return jsonify(body), status_code
        except Exception as e:
            current_app.logger.warning(f"Redis idempotency error: {e}")

        # Fallback to PostgreSQL
        db_response = self._get_from_db(idempotency_key)
        if db_response:
            # Restore to Redis for future fast access
            try:
                self.redis.setex(
                    cache_key,
                    self.DEFAULT_TTL_SECONDS,
                    json.dumps(db_response)
                )
            except Exception:
                pass  # Redis failure is not critical
            
            status_code = db_response.get('status', 200)
            body = db_response.get('body', {})
            return jsonify(body), status_code

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
                # Parse response data
                response_data = response.get_json()
                if response_data:
                    ttl = current_app.config.get('IDEMPOTENCY', {}).get('ttl_seconds', self.DEFAULT_TTL_SECONDS)
                    
                    # Cache with JSON (not pickle)
                    cache_data = {
                        'status_code': response.status_code,
                        'body': response_data
                    }
                    
                    # Save to Redis
                    self.redis.setex(
                        request.idempotency_cache_key,
                        ttl,
                        json.dumps(cache_data)
                    )
                    
                    # Also save to PostgreSQL (source of truth)
                    # Extract resource info from response if available
                    resource_type = request.path.split('/')[-1] if request.path else 'unknown'
                    resource_id = response_data.get('transaction_id') or response_data.get('id')
                    
                    self._save_to_db(
                        idempotency_key=request.idempotency_key,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        response_status=response.status_code,
                        response_body=response_data,
                        ttl_seconds=ttl
                    )
            except Exception as e:
                current_app.logger.warning(f"Idempotency cache store error: {e}")

        return response


# Create singleton instance
idempotency = IdempotencyMiddleware()
