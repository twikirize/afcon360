"""
app/wallet/middleware/wallet_activation.py
Check if user has an active wallet before allowing wallet operations.
"""

from functools import wraps
from flask import flash, redirect, url_for, request, current_app
from flask_login import current_user
from app.wallet.repositories.wallet_repository import WalletRepository


def require_wallet_activated(f):
    """
    Decorator to ensure user has an activated wallet.
    If not, redirect to wallet activation page.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access your wallet.", "warning")
            return redirect(url_for("auth_routes.login"))

        repo = WalletRepository()
        wallet = repo.get_by_user_id(current_user.id)

        if not wallet or not wallet.verified:
            # No wallet or wallet not activated
            flash("Please activate your wallet to access this feature.", "warning")
            return redirect(url_for("wallet_routes.activate_wallet"))

        return f(*args, **kwargs)

    return decorated_function


def wallet_exists() -> bool:
    """Check if current user has a wallet (doesn't require activation)."""
    if not current_user.is_authenticated:
        return False
    repo = WalletRepository()
    return repo.get_by_user_id(current_user.id) is not None