"""
Runtime ID Guard - Catches mistakes in development

DUAL ID SYSTEM ENFORCEMENT:
- Internal `id` (BIGINT): Used for database relationships and foreign keys
- External `public_id` (UUID string): Used for APIs, sessions, and URLs

This guard ensures:
1. Most `_id` foreign keys use BIGINT (referencing `users.id`)
2. Exceptions like `UserProfile.user_id` use UUID string (referencing `users.public_id`)
3. Public IDs follow proper UUID format
4. Development-time violations are caught and logged
"""

from functools import wraps
from flask import current_app, request, g, flash
import traceback
import re


class IDGuard:
    """Runtime protection against ID mixing"""

    _enabled = False

    # Fields that are allowed to be String foreign keys (reference public_id)
    STRING_FK_EXCEPTIONS = {
        # (ModelName, field_name): "referenced_table.referenced_column"
        ('UserProfile', 'user_id'): 'users.public_id',
        # Add other exceptions here as needed:
        # ('SomeModel', 'some_field'): 'users.public_id',
    }

    # Foreign keys that should be checked even if they don't end with '_id'
    ADDITIONAL_FK_FIELDS = {
        # 'field_name': 'referenced_table.referenced_column'
        'created_by': 'users.id',
        'updated_by': 'users.id',
        'assigned_by': 'users.id',
        'reviewed_by': 'users.id',
        'approved_by': 'users.id',
        'owner_id': 'users.id',
        'organizer_id': 'users.id',
    }

    @classmethod
    def enable(cls):
        """Enable runtime checking (development only)"""
        # Enable if not in production mode
        try:
            cls._enabled = not current_app.config.get('PRODUCTION', False)
        except RuntimeError:
            # Outside of application context
            cls._enabled = False

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if IDGuard is currently enabled"""
        return cls._enabled

    @classmethod
    def check_fk_assignment(cls, model_name: str, fk_field: str, value, source: str) -> bool:
        """
        Check if a foreign key assignment is correct.

        Args:
            model_name: Name of the model class
            fk_field: Name of the foreign key field
            value: The value being assigned
            source: Description of where the assignment occurred

        Returns:
            True if assignment is valid, False otherwise
        """
        if not cls._enabled:
            return True

        # Skip if value is None (nullable FK)
        if value is None:
            return True

        # Check if this is a String FK exception
        exception_key = (model_name, fk_field)
        if exception_key in cls.STRING_FK_EXCEPTIONS:
            # This FK references a UUID string (public_id)
            if not isinstance(value, str):
                cls._log_violation(
                    f"Foreign key {model_name}.{fk_field} assigned non-string {value}",
                    f"Expected str (UUID), got {type(value).__name__}",
                    source
                )
                return False
            # Validate it looks like a UUID
            return cls.check_public_id(value, source)

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
    def check_public_id(cls, value, source: str) -> bool:
        """
        Check if a public ID is a proper UUID.

        Args:
            value: The value being assigned
            source: Description of where the assignment occurred

        Returns:
            True if valid UUID format, False otherwise
        """
        if not cls._enabled:
            return True

        if value is None:
            return True

        # UUID v4 pattern (standard format)
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'

        # Also accept simple UUID format (less strict for development)
        simple_uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

        str_value = str(value)

        if not (re.match(uuid_pattern, str_value, re.I) or re.match(simple_uuid_pattern, str_value, re.I)):
            cls._log_violation(
                f"Public ID is not a valid UUID: {value}",
                "Expected UUID format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)",
                source
            )
            return False

        return True

    @classmethod
    def check_internal_id(cls, value, source: str) -> bool:
        """
        Check if an internal ID is a proper BIGINT.

        Args:
            value: The value being assigned
            source: Description of where the assignment occurred

        Returns:
            True if valid internal ID, False otherwise
        """
        if not cls._enabled:
            return True

        if value is None:
            return True

        if not isinstance(value, int):
            cls._log_violation(
                f"Internal ID is not an integer: {value}",
                f"Expected int (BIGINT), got {type(value).__name__}",
                source
            )
            return False

        if value <= 0:
            cls._log_violation(
                f"Internal ID has invalid value: {value}",
                "Expected positive integer",
                source
            )
            return False

        return True

    @classmethod
    def check_session_user_id(cls, value, source: str) -> bool:
        """
        Check that session['user_id'] contains a UUID (public_id), not BIGINT.

        Args:
            value: The value being stored in session
            source: Description of where the assignment occurred

        Returns:
            True if valid UUID, False otherwise
        """
        if not cls._enabled:
            return True

        if value is None:
            return True

        # Session should store public_id (UUID), not internal id (BIGINT)
        if isinstance(value, int):
            cls._log_violation(
                f"Session user_id contains integer {value} instead of UUID",
                "Session should store user.public_id (UUID), not user.id (BIGINT)",
                source
            )
            return False

        return cls.check_public_id(value, source)

    @classmethod
    def _log_violation(cls, error: str, suggestion: str, source: str):
        """
        Log a violation and show front-end alert if possible.
        """
        msg = f"\n🔴 ID SYSTEM VIOLATION: {error}\n   Suggestion: {suggestion}\n   Source: {source}"
        print(msg)

        # Show flash message if in request context
        try:
            flash(f"ID System Error: {error}. Suggestion: {suggestion}", "danger")
        except:
            pass

        # Print stack trace for debugging
        print("   Stack:")
        for line in traceback.format_stack()[:-2]:
            print(f"     {line.strip()}")

        # In development, raise exception to halt execution
        try:
            if not current_app.config.get('PRODUCTION', False):
                raise RuntimeError(f"ID System Violation: {error}. Suggestion: {suggestion}")
        except RuntimeError:
            # Outside app context, just raise
            raise RuntimeError(f"ID System Violation: {error}. Suggestion: {suggestion}")

    @classmethod
    def add_string_fk_exception(cls, model_name: str, field_name: str, references: str):
        """
        Add a new String FK exception at runtime.

        Args:
            model_name: Name of the model class
            field_name: Name of the foreign key field
            references: What this field references (e.g., 'users.public_id')
        """
        cls.STRING_FK_EXCEPTIONS[(model_name, field_name)] = references

    @classmethod
    def get_violation_summary(cls) -> dict:
        """
        Get a summary of IDGuard configuration for debugging.
        """
        return {
            'enabled': cls._enabled,
            'string_fk_exceptions': [f"{m}.{f} -> {r}" for (m, f), r in cls.STRING_FK_EXCEPTIONS.items()],
            'additional_fk_fields': list(cls.ADDITIONAL_FK_FIELDS.keys()),
        }


# ============================================================================
# Decorators
# ============================================================================

def guard_fk_assignment(f):
    """
    Decorator to check FK assignments before model save.
    Apply to model __init__ or save methods.
    """
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        # Check all FK fields before saving
        for column in self.__table__.columns:
            should_check = False

            # Check fields ending with '_id' (except 'id' itself)
            if column.name.endswith('_id') and column.name != 'id':
                should_check = True
            # Check additional FK fields
            elif column.name in IDGuard.ADDITIONAL_FK_FIELDS:
                should_check = True

            if should_check:
                value = getattr(self, column.name, None)
                if value is not None:
                    IDGuard.check_fk_assignment(
                        self.__class__.__name__,
                        column.name,
                        value,
                        f"Model {self.__class__.__name__}.{column.name}"
                    )
        return f(self, *args, **kwargs)
    return wrapper


def guard_session_user_id(f):
    """
    Decorator to ensure session['user_id'] contains a UUID, not BIGINT.
    Apply to login routes.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        result = f(*args, **kwargs)

        # Check session after login
        try:
            from flask import session
            if 'user_id' in session:
                IDGuard.check_session_user_id(
                    session['user_id'],
                    f"Session assignment in {f.__name__}"
                )
        except RuntimeError:
            pass  # Not in request context

        return result
    return wrapper


# ============================================================================
# Initialization
# ============================================================================

def init_id_guard(app):
    """
    Initialize IDGuard with Flask app.
    Call this in create_app().

    Args:
        app: Flask application instance
    """
    # Enable based on environment
    if not app.config.get('PRODUCTION', False):
        IDGuard.enable()
        app.logger.info(f"🛡️ IDGuard enabled with {len(IDGuard.STRING_FK_EXCEPTIONS)} String FK exceptions")
    else:
        app.logger.info("🛡️ IDGuard disabled (production mode)")


# ============================================================================
# CLI Command
# ============================================================================

def register_id_guard_commands(app):
    """Register Flask CLI commands for IDGuard."""

    @app.cli.command("id-guard-status")
    def id_guard_status():
        """Show IDGuard configuration status."""
        summary = IDGuard.get_violation_summary()
        print("\n🛡️ IDGuard Status")
        print("=" * 50)
        print(f"Enabled: {summary['enabled']}")
        print(f"\nString FK Exceptions ({len(summary['string_fk_exceptions'])}):")
        for exc in summary['string_fk_exceptions']:
            print(f"  • {exc}")
        print(f"\nAdditional FK Fields ({len(summary['additional_fk_fields'])}):")
        for field in summary['additional_fk_fields']:
            print(f"  • {field}")
        print()

    @app.cli.command("id-guard-add-exception")
    def id_guard_add_exception():
        """Add a String FK exception: flask id-guard-add-exception ModelName field_name references"""
        import sys
        if len(sys.argv) < 5:
            print("Usage: flask id-guard-add-exception ModelName field_name references")
            print("Example: flask id-guard-add-exception UserProfile user_id users.public_id")
            return

        model = sys.argv[2]
        field = sys.argv[3]
        refs = sys.argv[4]
        IDGuard.add_string_fk_exception(model, field, refs)
        print(f"✅ Added exception: ({model}, {field}) -> {refs}")
