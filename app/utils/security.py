#app/utilities/security
"""
Security utilities for sensitive data encryption and protection.
"""
import os
import re
import secrets
import string
import hashlib
import base64
from typing import Optional, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import g, request, current_app
from functools import wraps
from app.utils.exceptions import PermissionError

def _is_deployed_environment(app_env=None, flask_env=None) -> bool:
    """Fail closed when deployment mode is explicit or environment is unspecified."""
    app_env = str(
        app_env if app_env is not None else os.getenv("APP_ENV", "")
    ).strip().lower()
    flask_env = str(
        flask_env if flask_env is not None else os.getenv("FLASK_ENV", "")
    ).strip().lower()
    return (
        app_env in ("docker", "prod", "production")
        or flask_env == "production"
        or not (app_env or flask_env)
    )


def ensure_secret_key_configured(secret_key=None, app_env=None, flask_env=None):
    """Require a non-placeholder Flask signing key in deployed environments.

    The APP_ENV docker/prod setting is authoritative even when someone
    accidentally sets FLASK_ENV=development inside a deployed container.
    Local development may continue to use the documented development fallback.
    """
    candidate = str(secret_key or "").strip()
    if candidate and not candidate.startswith("REPLACE_"):
        return candidate

    if _is_deployed_environment(app_env, flask_env):
        raise RuntimeError(
            "SECRET_KEY must be configured before starting a deployed "
            "AFCON360 application. A deterministic development signing key "
            "is never permitted in Docker or production."
        )
    return None


def ensure_encryption_key_configured(app_env=None, flask_env=None) -> str:
    """Require a persistent key in deployed environments.

    Local development may receive an ephemeral process key, but that key is
    never logged and must not be mistaken for a durable deployment secret.
    """
    key_env = os.getenv("ENCRYPTION_KEY", "").strip()
    if key_env and not key_env.startswith("REPLACE_"):
        return key_env

    if _is_deployed_environment(app_env, flask_env):
        raise RuntimeError(
            "ENCRYPTION_KEY must be configured before starting a deployed "
            "AFCON360 application. Preserve the existing key; do not generate "
            "a replacement without re-encrypting stored secrets."
        )

    key_env = secrets.token_urlsafe(32)
    os.environ["ENCRYPTION_KEY"] = key_env
    import warnings
    warnings.warn(
        "ENCRYPTION_KEY was not configured. A temporary local-development "
        "key was generated; encrypted data will not survive a process restart.",
        RuntimeWarning,
    )
    return key_env


# Use environment variable for encryption key
def get_encryption_key():
    """Get encryption key from environment. Raises error if not set in production."""
    key_env = os.getenv("ENCRYPTION_KEY")
    if key_env and key_env.startswith("REPLACE_"):
        key_env = None

    if not key_env:
        # Docker is AFCON360's production deployment mode on the Oracle host.
        if _is_deployed_environment():
            raise RuntimeError(
                "ENCRYPTION_KEY must be configured for deployed environments. "
                "Provide the existing protected key; do not generate a replacement "
                "without re-encrypting all stored secrets."
            )
        else:
            # Development fallback with warning
            import warnings
            warnings.warn(
                "ENCRYPTION_KEY not set. Using development-only key. "
                "Set ENCRYPTION_KEY environment variable for production.",
                RuntimeWarning
            )
            # Generate a persistent development key from a known seed
            dev_key = hashlib.sha256(b"afcon360_development_key_do_not_use_in_production").digest()
            return base64.urlsafe_b64encode(dev_key)

    # Convert to 32-byte key for Fernet
    return base64.urlsafe_b64encode(hashlib.sha256(key_env.encode()).digest())

# Global encryption instance — lazily initialised on first use.
# NOT instantiated at module level because this file is imported before
# create_app() runs, which means before .env.local/.env.docker/.env.prod
# has been loaded. Calling get_encryption_key() here would crash with
# "ENCRYPTION_KEY not set" even when the key exists in .env.local.
_fernet = None


def _get_fernet() -> Fernet:
    """Return the Fernet instance, initialising it on first call."""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_encryption_key())
    return _fernet

def encrypt_field(data: str) -> str:
    """
    Encrypt sensitive field data.

    Args:
        data: Plain text string to encrypt

    Returns:
        Base64 encoded encrypted string
    """
    if not data:
        return ""
    try:
        encrypted = _get_fernet().encrypt(data.encode())
        return encrypted.decode('utf-8')
    except Exception as e:
        # Log error and return original data
        print(f"Encryption error: {e}")
        return data

def decrypt_field(encrypted_data: str) -> str:
    """
    Decrypt sensitive field data.

    Args:
        encrypted_data: Base64 encoded encrypted string

    Returns:
        Decrypted plain text string
    """
    if not encrypted_data:
        return ""
    try:
        decrypted = _get_fernet().decrypt(encrypted_data.encode())
        return decrypted.decode('utf-8')
    except Exception as e:
        # Log error and return original data
        print(f"Decryption error: {e}")
        return encrypted_data

def hash_field(data: str, salt: bytes = None) -> tuple:
    """
    Hash a field for storage (e.g., passwords).

    Args:
        data: Data to hash
        salt: Optional salt bytes

    Returns:
        Tuple of (hashed_data, salt)
    """
    if salt is None:
        salt = os.urandom(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA512(),
        length=64,
        salt=salt,
        iterations=480000,  # OWASP 2023 recommendation
    )

    key = base64.urlsafe_b64encode(kdf.derive(data.encode()))
    return key.decode('utf-8'), salt

# === ADDITIONAL FUNCTIONS NEEDED BY TRANSPORT MODULE ===

def verify_permission(user: object, permission: str, resource: Optional[object] = None) -> bool:
    """
    Verify if a user has a specific permission.

    Uses app/auth/helpers.py which queries the database directly - safe to call
    even on detached user objects loaded by Flask-Login in a previous session.

    Args:
        user: User object (Flask-Login current_user is safe)
        permission: Permission string to check (e.g., 'transport.booking.create')
        resource: Optional resource object for context-specific permissions

    Returns:
        Boolean indicating if permission is granted
    """
    if not user or not permission:
        return False

    # Import here to avoid circular imports at module load time
    from app.auth.helpers import has_global_permission, is_owner

    # Owner bypass
    if is_owner(user):
        return True

    # Use the DB-querying helper - never walks lazy-loaded relationships
    return has_global_permission(user, permission)


# Add this function to app/utils/security.py
def require_permission(permission: str):
    """
    Decorator to require a specific permission for endpoint access.

    Args:
        permission: Permission string required (e.g., 'settings:read')

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get current user (adapt based on your auth system)
            user = None

            # Try to get user from Flask-Login
            try:
                from flask_login import current_user
                if current_user and current_user.is_authenticated:
                    user = current_user
            except ImportError:
                pass

            # Try to get user from Flask g context
            if not user and hasattr(g, 'user'):
                user = g.user

            # Try to get user from session
            if not user and hasattr(request, 'session'):
                user = request.session.get('user')

            # Verify permission
            if not verify_permission(user, permission):
                raise PermissionError(
                    message=f"Permission denied: {permission}",
                    user_id=getattr(user, 'id', None) or getattr(user, 'user_id', None),
                    required_permission=permission
                )

            return func(*args, **kwargs)

        return wrapper

    return decorator

def sanitize_input(input_str: str, allowed_chars: Optional[str] = None) -> str:
    """
    Sanitize input string by removing potentially dangerous characters.

    Args:
        input_str: Input string to sanitize
        allowed_chars: Optional string of allowed characters (regex pattern)

    Returns:
        Sanitized string
    """
    if not input_str:
        return ""

    # Remove null bytes
    input_str = input_str.replace('\x00', '')

    # Remove control characters (except newline, tab, etc.)
    input_str = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', input_str)

    # Remove HTML/script tags
    input_str = re.sub(r'<[^>]*>', '', input_str)

    # Remove SQL injection patterns (basic)
    sql_patterns = [
        r'(\b(select|insert|update|delete|drop|alter|create|exec|union)\b)',
        r'(\-\-|\#)',  # SQL comments
        r'(\;\s*|\'|\")',  # SQL statement terminators and quotes
    ]

    for pattern in sql_patterns:
        input_str = re.sub(pattern, '', input_str, flags=re.IGNORECASE)

    # If allowed characters specified, filter to only those
    if allowed_chars:
        pattern = f'[^{re.escape(allowed_chars)}]'
        input_str = re.sub(pattern, '', input_str)

    return input_str.strip()

def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure token.

    Args:
        length: Length of token in bytes

    Returns:
        URL-safe base64 encoded token
    """
    return secrets.token_urlsafe(length)

def validate_csrf(token: Optional[str] = None) -> bool:
    """
    Validate CSRF token from request.

    Args:
        token: Optional token to validate (uses request by default)

    Returns:
        Boolean indicating if token is valid
    """
    try:
        from flask_wtf.csrf import validate_csrf as wtf_validate_csrf

        if token is None and request:
            # Get token from request
            if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                token = request.form.get('csrf_token') or \
                       request.headers.get('X-CSRF-Token') or \
                       request.cookies.get('csrf_token')

        if token:
            wtf_validate_csrf(token)
            return True

    except Exception as e:
        current_app.logger.warning(f"CSRF validation failed: {e}")

    return False

def generate_password(length: int = 12) -> str:
    """
    Generate a secure random password.

    Args:
        length: Length of password

    Returns:
        Secure password string
    """
    if length < 8:
        length = 8

    # Character sets
    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*()_+-=[]{}|;:,.<>?"

    # Ensure at least one of each type
    password = [
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(symbols)
    ]

    # Fill remaining length with random choices from all sets
    all_chars = uppercase + lowercase + digits + symbols
    password += [secrets.choice(all_chars) for _ in range(length - 4)]

    # Shuffle to randomize position of required characters
    secrets.SystemRandom().shuffle(password)

    return ''.join(password)

def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Validate password strength.

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"

    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', password):
        return False, "Password must contain at least one special character"

    # Check for common patterns
    common_patterns = [
        r'123456',
        r'password',
        r'qwerty',
        r'admin',
        r'welcome',
        r'abcdef',
    ]

    password_lower = password.lower()
    for pattern in common_patterns:
        if pattern in password_lower:
            return False, "Password contains common pattern"

    # Check for repeated characters
    if re.search(r'(.)\1{3,}', password):
        return False, "Password contains too many repeated characters"

    return True, "Password is strong"

def hash_password(password: str) -> Tuple[str, str]:
    """
    Hash a password for storage.

    Args:
        password: Plain text password

    Returns:
        Tuple of (hashed_password, salt_encoded)
    """
    salt = os.urandom(16)
    hashed, salt = hash_field(password, salt)
    return hashed, base64.b64encode(salt).decode('utf-8')

def verify_password(password: str, hashed_password: str, salt_encoded: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        password: Plain text password to verify
        hashed_password: Stored hashed password
        salt_encoded: Base64 encoded salt

    Returns:
        Boolean indicating if password matches
    """
    try:
        salt = base64.b64decode(salt_encoded)
        new_hash, _ = hash_field(password, salt)
        return secrets.compare_digest(new_hash, hashed_password)
    except Exception:
        return False

def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive data for logging/display.

    Args:
        data: Sensitive data to mask
        visible_chars: Number of characters to leave visible at end

    Returns:
        Masked string
    """
    if not data or len(data) <= visible_chars:
        return "***"

    visible = data[-visible_chars:]
    return f"{'*' * (len(data) - visible_chars)}{visible}"

def generate_api_key(prefix: str = "afcon") -> str:
    """
    Generate a secure API key.

    Args:
        prefix: Optional prefix for the key

    Returns:
        API key string
    """
    key = secrets.token_urlsafe(32)
    if prefix:
        return f"{prefix}_{key}"
    return key

def validate_email(email: str) -> bool:
    """
    Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        Boolean indicating if email is valid
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_phone(phone: str) -> bool:
    """
    Validate phone number format.

    Args:
        phone: Phone number to validate

    Returns:
        Boolean indicating if phone number is valid
    """
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)

    # Check for reasonable length (usually 10-15 digits)
    return 10 <= len(digits) <= 15