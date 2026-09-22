#app/utils/exceptions.py
"""
Custom exceptions for AFCON360
"""

class ValidationError(Exception):
    """Raised when validation fails"""
    def __init__(self, message="Validation failed", field=None, value=None, code=None, details=None):
        self.message = message
        self.field = field
        self.value = value
        self.code = code
        self.details = details
        super().__init__(self.message)

class AuthorizationError(Exception):
    """Raised when a user lacks permission for an operation."""
    def __init__(self, message="Permission denied", user_id=None, required_permission=None, code=None, details=None):
        self.message = message
        self.user_id = user_id
        self.required_permission = required_permission
        self.code = code
        self.details = details
        super().__init__(self.message)

# Backward-compatible alias. New code should import AuthorizationError.
# Existing imports of `PermissionError` from this module keep working.
PermissionError = AuthorizationError
class RateLimitError(Exception):
    """Raised when rate limit is exceeded"""
    def __init__(self, message="Rate limit exceeded", limit=None, window=None, code=None, details=None):
        self.message = message
        self.limit = limit
        self.window = window
        self.code = code
        self.details = details
        super().__init__(self.message)


class ServiceUnavailableError(Exception):
    """Raised when a service is unavailable"""
    def __init__(self, message="Service unavailable", service_name=None, retry_after=None, code=None, details=None):
        self.message = message
        self.service_name = service_name
        self.retry_after = retry_after
        self.code = code
        self.details = details
        super().__init__(self.message)

class ConflictError(Exception):
    """Raised when there's a data conflict"""
    def __init__(self, message="Conflict detected", resource=None, conflict_type=None, code=None, details=None):
        self.message = message
        self.resource = resource
        self.conflict_type = conflict_type
        self.code = code
        self.details = details
        super().__init__(self.message)

class NotFoundError(Exception):
    """Raised when resource is not found"""
    def __init__(self, message="Resource not found", resource_type=None, resource_id=None, code=None, details=None):
        self.message = message
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.code = code
        self.details = details
        super().__init__(self.message)

class DatabaseError(Exception):
    """Raised for database-related errors"""
    def __init__(self, message="Database error", operation=None, constraint=None, code=None, details=None):
        self.message = message
        self.operation = operation
        self.constraint = constraint
        self.code = code
        self.details = details
        super().__init__(self.message)

class AuthenticationError(Exception):
    """Raised when authentication fails"""
    def __init__(self, message="Authentication failed", reason=None, code=None, details=None):
        self.message = message
        self.reason = reason
        self.code = code
        self.details = details
        super().__init__(self.message)

class BusinessLogicError(Exception):
    """Raised when business logic rules are violated"""
    def __init__(self, message="Business logic error", rule=None, context=None, code=None, details=None):
        self.message = message
        self.rule = rule
        self.context = context
        self.code = code
        self.details = details
        super().__init__(self.message)
class ExternalServiceError(Exception):
    """Raised when external service calls fail"""
    def __init__(self, message="External service error", service=None, status_code=None, code=None, details=None):
        self.message = message
        self.service = service
        self.status_code = status_code
        self.code = code
        self.details = details
        super().__init__(self.message)
