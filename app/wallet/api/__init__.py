"""
app/wallet/api/__init__.py
Wallet API module - REST endpoints for wallet operations.
"""

from app.wallet.api.wallet_api import wallet_api_bp
from app.wallet.api.admin_api import admin_wallet_bp
from app.wallet.api.webhook_api import webhook_bp
from app.wallet.api.audit_api import audit_bp
__all__ = [
    'wallet_api_bp',
    'admin_wallet_bp',
    'webhook_bp',
    'audit_bp',
]
