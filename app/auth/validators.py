# app/auth/validators.py
import re

RESERVED_USERNAMES = {"admin", "root", "system"}

def validate_registration(username, password, email=None):
    # Username rules
    if not (3 <= len(username) <= 30):
        return False, "Username must be 3-30 characters long"
    if username.lower() in RESERVED_USERNAMES:
        return False, "This username is reserved"
    if not re.match(r"^[a-zA-Z0-9_.\-]+$", username):
        return False, "Username may only contain letters, numbers, underscores, dots, or hyphens"

    # Password rules
    if len(password) < 10:
        return False, "Password must be at least 10 characters long"
    categories = [r"[A-Z]", r"[a-z]", r"\d", r"[^A-Za-z0-9]"]
    if sum(bool(re.search(p, password)) for p in categories) < 3:
        return False, "Password must include at least 3 of: uppercase, lowercase, number, symbol"

    # Email rules
    if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return False, "Invalid email format"

    return True, ""

def validate_security_answer(answer):
    """
    Validate security answer.
    Returns: (is_valid, error_message)
    """
    if not answer or len(answer.strip()) == 0:
        return False, "Security answer cannot be empty"

    if len(answer.strip()) < 2:
        return False, "Security answer must be at least 2 characters long"

    # Additional validation can be added here
    return True, ""
