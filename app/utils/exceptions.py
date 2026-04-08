#app/utils/exceptions.py
"""
Custom exceptions for AFCON360
"""

class ValidationError(Exception):
    """Raised when validation fails"""
    def __init__(self, message="Validation failed", field=None, value=None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(self.message)

class PermissionError(Exception):
    """Raised when user lacks permission"""
    def __init__(self, message="Permission denied", user_id=None, required_permission=None):
        self.message = message
        self.user_id = user_id
        self.required_permission = required_permission
        super().__init__(self.message)

class RateLimitError(Exception):
    """Raised when rate limit is exceeded"""
    def __init__(self, message="Rate limit exceeded", limit=None, window=None):
        self.message = message
        self.limit = limit
        self.window = window
        super().__init__(self.message)

class ServiceUnavailableError(Exception):
    """Raised when a service is unavailable"""
    def __init__(self, message="Service unavailable", service_name=None, retry_after=None):
        self.message = message
        self.service_name = service_name
        self.retry_after = retry_after
        super().__init__(self.message)

class ConflictError(Exception):
    """Raised when there's a data conflict"""
    def __init__(self, message="Conflict detected", resource=None, conflict_type=None):
        self.message = message
        self.resource = resource
        self.conflict_type = conflict_type
        super().__init__(self.message)

class NotFoundError(Exception):
    """Raised when resource is not found"""
    def __init__(self, message="Resource not found", resource_type=None, resource_id=None):
        self.message = message
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(self.message)

class DatabaseError(Exception):
    """Raised for database-related errors"""
    def __init__(self, message="Database error", operation=None, constraint=None):
        self.message = message
        self.operation = operation
        self.constraint = constraint
        super().__init__(self.message)

class AuthenticationError(Exception):
    """Raised when authentication fails"""
    def __init__(self, message="Authentication failed", reason=None):
        self.message = message
        self.reason = reason
        super().__init__(self.message)

class BusinessLogicError(Exception):
    """Raised when business logic rules are violated"""
    def __init__(self, message="Business logic error", rule=None, context=None):
        self.message = message
        self.rule = rule
        self.context = context
        super().__init__(self.message)

class ExternalServiceError(Exception):
    """Raised when external service calls fail"""
    def __init__(self, message="External service error", service=None, status_code=None):
        self.message = message
        self.service = service
        self.status_code = status_code
        super().__init__(self.message)
