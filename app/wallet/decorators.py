"""
Decorators to enforce Account-ID-First pattern across system.

This enforces Alipay model across all wallet operations.
"""

from functools import wraps
from flask import jsonify, current_app, flash, redirect, url_for
from uuid import UUID

from app.wallet.exceptions import WalletNotFoundError


def require_account_id(f):
    """
    Decorator to ensure method receives account_id (UUID), not user_id.
    
    This enforces Alipay model across all wallet operations.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'account_id' not in kwargs and len(args) > 0:
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
            setattr(cls, method_name, require_account_id(method))
    
    return cls


def require_sufficient_kyc(feature=None):
    """
    Decorator to enforce KYC-based access control.
    
    Args:
        feature: Optional feature name for logging
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from app.wallet.services.kyc_limit_service import KYCLimitService
            
            action_map = {
                'send': 'send',
                'withdraw': 'withdraw',
                'deposit': 'deposit',
                'transfer': 'send'
            }
            
            action = action_map.get(feature or f.__name__, 'send')
            
            result = KYCLimitService.check_transaction_allowed(
                user_id=current_user.id,
                amount=kwargs.get('amount', Decimal('0')),
                action=action
            )
            
            if not result['allowed']:
                flash(result.get('reason', 'KYC verification required for this action.'), 'warning')
                return redirect(url_for('wallet.wallet_dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_transaction_verification(f):
    """
    Decorator to require identity verification for sensitive transaction actions.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.wallet.services.identity_verification_service import IdentityVerificationService
        
        action_map = {
            'send_funds': 'large_transfer',
            'withdraw_funds': 'large_withdrawal',
            'deposit_form': 'deposit'
        }
        
        action_type = action_map.get(f.__name__, 'large_transfer')
        verification = IdentityVerificationService.require_verification(action_type)
        
        if verification.get('required'):
            flash('Identity verification required for this transaction. Please complete verification.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def require_no_freeze(f):
    """
    Decorator to ensure account is not frozen.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.wallet.models.ledger import AccountModel
        
        account = AccountModel.query.filter_by(
            user_id=current_user.id
        ).first()
        
        if account and account.is_frozen:
            flash(f'Account is frozen: {account.frozen_reason or "Contact support for assistance."}', 'danger')
            return redirect(url_for('wallet.wallet_dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function
