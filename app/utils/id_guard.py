"""
Runtime ID Guard - Catches mistakes in development
"""

from functools import wraps
from flask import current_app, request, g, flash
import traceback


class IDGuard:
    """Runtime protection against ID mixing"""

    _enabled = False

    @classmethod
    def enable(cls):
        """Enable runtime checking (development only)"""
        # Enable if not in production mode
        cls._enabled = not current_app.config.get('PRODUCTION', False)

    @classmethod
    def check_fk_assignment(cls, model_name, fk_field, value, source):
        """Check if a foreign key assignment is correct"""
        if not cls._enabled:
            return True

        # Skip if value is None
        if value is None:
            return True

        # Check 1: FK must be integer (BIGINT)
        if not isinstance(value, int):
            cls._log_violation(
                f"Foreign key {model_name}.{fk_field} assigned non-integer {value}",
                f"Expected int (BIGINT), got {type(value).__name__}",
                source
            )
            return False

        # Check 2: Value should be reasonable (positive)
        if value <= 0:
            cls._log_violation(
                f"Foreign key {model_name}.{fk_field} assigned invalid value {value}",
                "Expected positive integer",
                source
            )
            return False

        return True

    @classmethod
    def check_public_id(cls, value, source):
        """Check if a public ID is a proper UUID"""
        if not cls._enabled:
            return True

        if value is None:
            return True

        import re
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

        if not re.match(uuid_pattern, str(value), re.I):
            cls._log_violation(
                f"Public ID is not a valid UUID: {value}",
                "Expected UUID format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)",
                source
            )
            return False

        return True

    @classmethod
    def _log_violation(cls, error, suggestion, source):
        """Log a violation and show front-end alert if possible"""
        msg = f"🔴 ID SYSTEM VIOLATION: {error}\n   Suggestion: {suggestion}\n   Source: {source}"
        print(f"\n{msg}")

        # Show flash message if in request context
        try:
            flash(f"ID System Error: {error}. Suggestion: {suggestion}", "danger")
        except:
            pass

        print(f"   Stack:")
        for line in traceback.format_stack()[:-2]:
            print(f"     {line.strip()}")

        # In development, raise exception to halt execution
        if not current_app.config.get('PRODUCTION', False):
            raise RuntimeError(f"ID System Violation: {error}. Suggestion: {suggestion}")


# Decorator for model save operations
def guard_fk_assignment(f):
    """Decorator to check FK assignments before save"""
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        # Check all FK fields before saving
        for column in self.__table__.columns:
            if column.name.endswith('_id') and column.name != 'id':
                value = getattr(self, column.name)
                if value is not None:
                    IDGuard.check_fk_assignment(
                        self.__class__.__name__,
                        column.name,
                        value,
                        f"Model {self.__class__.__name__}.{column.name}"
                    )
        return f(self, *args, **kwargs)
    return wrapper
