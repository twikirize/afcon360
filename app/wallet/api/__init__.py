"""
app/wallet/api/__init__.py
Wallet API module - REST endpoints for wallet operations.
"""

from app.wallet.api.wallet_api import wallet_api_bp
from app.wallet.api.fx_api import fx_api_bp

__all__ = [
    'wallet_api_bp',
    'fx_api_bp',
]
