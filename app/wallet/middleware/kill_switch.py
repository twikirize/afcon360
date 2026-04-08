"""
app/wallet/middleware/kill_switch.py
Simple kill switch - ONE toggle turns entire wallet ON/OFF.
"""

from functools import wraps
from flask import current_app, jsonify
from flask_login import current_user


def wallet_enabled() -> bool:
    """
    Check if wallet module is enabled.
    Reads from config - can be changed at runtime via environment variable.
    """
    return current_app.config.get("MODULE_FLAGS", {}).get("wallet", True)


def require_wallet_enabled(f):
    """
    Decorator for wallet endpoints.
    Returns 503 with friendly message if wallet is disabled.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not wallet_enabled():
            return {
                "status": "error",
                "code": "WALLET_DISABLED",
                "message": "Wallet service is currently disabled. Please try again later."
            }, 503
        return f(*args, **kwargs)
    return decorated_function


def wallet_disabled_response():
    """Return standard disabled response for any wallet endpoint."""
    return {
        "status": "error",
        "code": "WALLET_DISABLED",
        "message": "Wallet service is currently disabled. Please try again later."
    }, 503
