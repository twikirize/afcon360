"""
Decorators to enforce Account-ID-First pattern across system.

This enforces Alipay model across all wallet operations.
"""

from functools import wraps
from flask import jsonify, current_app
from uuid import UUID

from app.wallet.exceptions import WalletNotFoundError


def require_account_id(f):
    """
    Decorator to ensure method receives account_id (UUID), not user_id.
    
    This enforces Alipay model across all wallet operations.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if account_id is in kwargs
        if 'account_id' not in kwargs and len(args) > 0:
            # First arg might be account_id
            first_arg = args[0]
            if isinstance(first_arg, int):
                raise TypeError(
                    f"Method {f.__name__}() received int (user_id). "
                    f"Use account_id (UUID) instead per Alipay model."
                )
        
        return f(*args, **kwargs)
    return decorated_function


def enforce_account_id_interface(cls):
    """
    Class decorator to enforce account_id methods on service classes.
    
    Ensures WalletService uses account_id pattern consistently.
    """
    expected_methods = ['deposit', 'withdraw', 'transfer', 'get_balance']
    
    for method_name in expected_methods:
        method = getattr(cls, method_name, None)
        if method:
            # Wrap with enforcement decorator
            setattr(cls, method_name, require_account_id(method))
    
    return cls
