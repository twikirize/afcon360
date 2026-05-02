"""
Wallet module initialization.
Exports the wallet blueprint and helper functions.
"""
from .routes import wallet_bp, get_or_create_account

__all__ = ['wallet_bp', 'get_or_create_account']