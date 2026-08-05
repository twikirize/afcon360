"""
KYC-based transaction limit service.

Enforces per-user transaction limits based on KYC level to comply with
regulatory requirements and reduce fraud risk.
"""

from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from flask import current_app
from flask_login import current_user

from app.extensions import db
from app.wallet.models.transaction import TransactionModel, TransactionStatus
from app.wallet.models.ledger import AccountModel
from app.wallet.exceptions import LimitExceededError


class KYCLimitService:
    """
    Service for managing KYC-based transaction limits.
    
    Limits are tiered by KYC level and enforced at the service layer
    to prevent unauthorized or excessive transactions.
    """

    LIMITS = {
        0: {
            'daily_limit': Decimal('0'),
            'monthly_limit': Decimal('0'),
            'per_txn_limit': Decimal('0'),
            'max_balance': Decimal('0'),
            'can_send': False,
            'can_receive': True,
            'can_withdraw': False,
            'can_deposit': True,
            'label': 'Unregistered'
        },
        1: {
            'daily_limit': Decimal('1000000'),
            'monthly_limit': Decimal('5000000'),
            'per_txn_limit': Decimal('500000'),
            'max_balance': Decimal('10000000'),
            'can_send': True,
            'can_receive': True,
            'can_withdraw': True,
            'can_deposit': True,
            'label': 'Basic'
        },
        2: {
            'daily_limit': Decimal('5000000'),
            'monthly_limit': Decimal('20000000'),
            'per_txn_limit': Decimal('2000000'),
            'max_balance': Decimal('50000000'),
            'can_send': True,
            'can_receive': True,
            'can_withdraw': True,
            'can_deposit': True,
            'label': 'Standard'
        },
        3: {
            'daily_limit': Decimal('20000000'),
            'monthly_limit': Decimal('100000000'),
            'per_txn_limit': Decimal('10000000'),
            'max_balance': Decimal('200000000'),
            'can_send': True,
            'can_receive': True,
            'can_withdraw': True,
            'can_deposit': True,
            'label': 'Enhanced'
        }
    }

    @classmethod
    def get_limits(cls, kyc_level: int) -> Dict[str, Any]:
        """Get limits for a given KYC level."""
        return cls.LIMITS.get(kyc_level, cls.LIMITS[0])

    @classmethod
    def get_user_kyc_level(cls, user_id: int) -> int:
        """Get effective KYC level for a user."""
        from app.identity.models.user import User
        user = db.session.get(User, user_id)
        if not user:
            return 0
        return getattr(user, 'kyc_level', 0) or 0

    @classmethod
    def check_transaction_allowed(
        cls,
        user_id: int,
        amount: Decimal,
        action: str,
        currency: str = 'UGX'
    ) -> Dict[str, Any]:
        """
        Check if a transaction is allowed based on KYC level.
        
        Args:
            user_id: Internal user ID
            amount: Transaction amount
            action: One of 'send', 'receive', 'withdraw', 'deposit'
            currency: Currency code
            
        Returns:
            Dict with 'allowed' (bool) and 'reason' (str if not allowed)
        """
        kyc_level = cls.get_user_kyc_level(user_id)
        limits = cls.get_limits(kyc_level)
        
        action_map = {
            'send': 'can_send',
            'receive': 'can_receive',
            'withdraw': 'can_withdraw',
            'deposit': 'can_deposit'
        }
        
        allowed_attr = action_map.get(action)
        if not allowed_attr:
            return {'allowed': False, 'reason': f'Unknown action: {action}'}
        
        if not limits.get(allowed_attr, False):
            return {
                'allowed': False,
                'reason': f'{action.capitalize()} not permitted at KYC level {limits["label"]} (level {kyc_level}). Complete KYC verification to unlock.'
            }
        
        if amount > limits['per_txn_limit']:
            return {
                'allowed': False,
                'reason': f'Per-transaction limit for {limits["label"]} tier is {limits["per_txn_limit"]:,.0f} {currency}. Amount: {amount:,.0f}'
            }
        
        return {'allowed': True}

    @classmethod
    def check_volume_limits(
        cls,
        account_id: str,
        amount: Decimal,
        currency: str,
        period: str = 'daily'
    ) -> Dict[str, Any]:
        """
        Check if a transaction would exceed daily/monthly volume limits.
        
        Args:
            account_id: Account UUID
            amount: Proposed transaction amount
            currency: Currency code
            period: 'daily' or 'monthly'
            
        Returns:
            Dict with 'allowed' (bool) and 'reason' (str if not allowed)
        """
        account = db.session.get(AccountModel, account_id)
        if not account:
            return {'allowed': False, 'reason': 'Account not found'}
        
        kyc_level = cls.get_user_kyc_level(account.user_id)
        limits = cls.get_limits(kyc_level)
        
        if period == 'daily':
            limit_key = 'daily_limit'
            volume_column = 'daily_volume'
            reset_column = 'daily_volume_reset_at'
        else:
            limit_key = 'monthly_limit'
            volume_column = 'monthly_volume'
            reset_column = 'monthly_volume_reset_at'
        
        limit = limits.get(limit_key, Decimal('0'))
        current_volume = getattr(account, volume_column, Decimal('0')) or Decimal('0')
        
        # Reset volume if period has elapsed
        reset_at = getattr(account, reset_column, None)
        if reset_at and datetime.now(timezone.utc) > reset_at:
            current_volume = Decimal('0')
            setattr(account, volume_column, Decimal('0'))
            setattr(account, reset_column, datetime.now(timezone.utc) + timedelta(days=1 if period == 'daily' else 30))
            db.session.commit()
        
        if current_volume + amount > limit:
            return {
                'allowed': False,
                'reason': f'{period.capitalize()} volume limit ({limit:,.0f} {currency}) exceeded. Current: {current_volume:,.0f}, Requested: {amount:,.0f}'
            }
        
        return {'allowed': True}

    @classmethod
    def get_transaction_limits(cls, user_id: int) -> Dict[str, Any]:
        """Get all applicable limits for a user."""
        kyc_level = cls.get_user_kyc_level(user_id)
        limits = cls.get_limits(kyc_level)
        
        return {
            'kyc_level': kyc_level,
            'kyc_label': limits['label'],
            'per_transaction_limit': float(limits['per_txn_limit']),
            'daily_limit': float(limits['daily_limit']),
            'monthly_limit': float(limits['monthly_limit']),
            'max_balance': float(limits['max_balance']),
            'features': {
                'send': limits['can_send'],
                'receive': limits['can_receive'],
                'withdraw': limits['can_withdraw'],
                'deposit': limits['can_deposit']
            }
        }

