#app/utils/__init__.py
"""
Core utilities and shared functionality for AFCON360.
"""
from app.utils.security import encrypt_field, decrypt_field
# Add these imports
from app.utils.exceptions import (
    ValidationError, PermissionError, RateLimitError,
    ServiceUnavailableError, ConflictError, NotFoundError,
    DatabaseError, AuthenticationError, BusinessLogicError, ExternalServiceError
)

from app.utils.monitoring import (
    monitor_endpoint, record_metric, start_span,
    track_operation, with_circuit_breaker,
    get_request_context, set_request_context
)

from app.utils.caching import (
    cached_query, invalidate_cache_pattern,
    with_cache_lock, cache_invalidate_on_change,
    get_cached, set_cached, delete_cached, clear_cache
)

from app.utils.audit import (
    audit_log, with_audit_log, AuditContext, AuditLog
)

from app.utils.rate_limiting import (
    rate_limit, get_rate_limiter, clear_rate_limits
)

from app.utils.idempotency import (
    idempotent_request, clear_idempotency_keys,
    cleanup_expired_idempotency_keys
)
from app.utils.security import (
    encrypt_field, decrypt_field, hash_field,
    verify_permission, sanitize_input,
    generate_secure_token, validate_csrf,
    generate_password, validate_password_strength,
    hash_password, verify_password,
    mask_sensitive_data, generate_api_key,
    validate_email, validate_phone
)
from app.utils.validators import(
    TransportValidators,
    validate_driver_registration,
    validate_vehicle_registration,
    validate_organisation_transport,
    validate_booking_request,
    validate_payment,
    validate_rating,
)

# Add to __all__ list
__all__ = [
    # ... existing items ...
    # Exceptions
    'ValidationError', 'PermissionError', 'RateLimitError',
    'ServiceUnavailableError', 'ConflictError', 'NotFoundError',
    'DatabaseError', 'AuthenticationError', 'BusinessLogicError', 'ExternalServiceError',
    # Monitoring
    'monitor_endpoint', 'record_metric', 'start_span',
    'track_operation', 'with_circuit_breaker',
    'get_request_context', 'set_request_context',
    # Caching
    'cached_query', 'invalidate_cache_pattern',
    'with_cache_lock', 'cache_invalidate_on_change',
    'get_cached', 'set_cached', 'delete_cached', 'clear_cache',
    # Audit
    'audit_log', 'with_audit_log', 'AuditContext', 'AuditLog',
    # Rate limiting
    'rate_limit', 'get_rate_limiter', 'clear_rate_limits',
    # Idempotency
    'idempotent_request', 'clear_idempotency_keys',
    'cleanup_expired_idempotency_keys',

    # Security functions
    'encrypt_field', 'decrypt_field', 'hash_field',
    'verify_permission', 'sanitize_input',
    'generate_secure_token', 'validate_csrf',
    'generate_password', 'validate_password_strength',
    'hash_password', 'verify_password',
    'mask_sensitive_data', 'generate_api_key',
    'validate_email', 'validate_phone',
    #Validators
    'TransportValidators',
    'validate_driver_registration',
    'validate_vehicle_registration',
    'validate_organisation_transport',
    'validate_booking_request',
    'validate_payment',
    'validate_rating',
]
