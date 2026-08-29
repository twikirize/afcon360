"""
KYC-based transaction limit service.

Enforces per-user transaction limits based on KYC level to comply with
regulatory requirements and reduce fraud risk.
"""

from decimal import Decimal
import decimal
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from flask import current_app
from flask_login import current_user

from app.extensions import db
from app.wallet.models.transaction import TransactionModel, TransactionStatus
from app.wallet.models.ledger import AccountModel
from app.wallet.models.config import WalletSystemConfig
from app.wallet.exceptions import LimitExceededError
from app.wallet.services.regulatory_volume_calculator import RegulatoryVolumeCalculator


class KYCLimitService:
    """
    Service for managing KYC-based transaction limits.
    
    Limits are tiered by KYC level and enforced at the service layer
    to prevent unauthorized or excessive transactions.
    
    Uses live KYC configuration from system_configs (via kyc_config_schema)
    as the single source of truth for limits.
    """

    # Tier feature matrix - defines what features are available at each tier
    # This is based on tier semantics, not configurable limits
    TIER_FEATURES = {
        0: {
            'can_send': False,
            'can_receive': True,
            'can_withdraw': False,
            'can_deposit': True,
            'label': 'Unregistered'
        },
        1: {
            'can_send': True,
            'can_receive': True,
            'can_withdraw': True,
            'can_deposit': True,
            'label': 'Basic'
        },
        2: {
            'can_send': True,
            'can_receive': True,
            'can_withdraw': True,
            'can_deposit': True,
            'label': 'Standard'
        },
        3: {
            'can_send': True,
            'can_receive': True,
            'can_withdraw': True,
            'can_deposit': True,
            'label': 'Enhanced'
        },
        4: {
            'can_send': True,
            'can_receive': True,
            'can_withdraw': True,
            'can_deposit': True,
            'label': 'Premium'
        },
        5: {
            'can_send': True,
            'can_receive': True,
            'can_withdraw': True,
            'can_deposit': True,
            'label': 'Corporate'
        }
    }

    @classmethod
    def _get_live_limits(cls, kyc_level: int) -> Dict[str, Any]:
        """Get live limits from KYC configuration (single source of truth)."""
        from app.kyc_config_schema import get_tier_requirements
        tier_reqs = get_tier_requirements()
        tier_config = tier_reqs.get(kyc_level, tier_reqs[0])
        
        return {
            'daily_limit': Decimal(str(tier_config.get('daily_limit', 0) or 0)),
            'monthly_limit': Decimal(str(tier_config.get('monthly_limit', 0) or 0)),
            'per_txn_limit': Decimal(str(tier_config.get('transaction_limit', 0) or 0)),
        }

    @classmethod
    def get_limits(cls, kyc_level: int) -> Dict[str, Any]:
        """Get limits for a given KYC level from live configuration."""
        live_limits = cls._get_live_limits(kyc_level)
        features = cls.TIER_FEATURES.get(kyc_level, cls.TIER_FEATURES[0])
        return {**live_limits, **features}

    @classmethod
    def _operational_per_txn_ceiling(cls, operational_config, action: str):
        """Return the action-specific operational per-transaction ceiling.

        The wallet system config defines distinct operational ceilings per action
        (deposit / withdrawal / transfer). These are NOT interchangeable with the
        daily or monthly cumulative limits (Issue A/H).
        """
        ceiling_map = {
            'deposit': operational_config.max_deposit_amount,
            'withdraw': operational_config.max_withdrawal_amount,
            'send': operational_config.max_transfer_amount,
            'receive': operational_config.max_transfer_amount,
        }
        return ceiling_map.get(action, operational_config.max_transfer_amount)

    @classmethod
    def get_user_kyc_level(cls, user_id: int) -> int:
        """Get effective KYC level for a user from canonical authority."""
        from app.auth.kyc_compliance import calculate_kyc_tier
        kyc_info = calculate_kyc_tier(user_id)
        return kyc_info["tier"]

    @classmethod
    def check_transaction_allowed(
        cls,
        user_id: int,
        amount: Decimal,
        action: str,
        currency: str = 'UGX',
        recipient_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Check if a transaction is allowed based on KYC level.

        Args:
            user_id: Internal user OR organisation ID (organisation wallets use the
                     organisation id as the account owner).
            amount: Transaction amount
            action: One of 'send', 'receive', 'withdraw', 'deposit'
            currency: Currency code
            recipient_user_id: Optional recipient owner id, used to detect a
                     "personal transfer" (organ -> individual) which forces full KYB.

        Returns:
            Dict with 'allowed' (bool) and 'reason' (str if not allowed).
        """
        # ── Organisation KYB gating ──
        # An organisation wallet's user_id is the organisation id, so a lookup
        # that misses User resolves to an Organisation. Org KYB rules then apply.
        from app.identity.models.organisation import Organisation
        org = db.session.get(Organisation, user_id)
        if org is not None and not getattr(org, "is_deleted", False):
            return cls._check_org_transaction_allowed(org, amount, action, currency, recipient_user_id)

        kyc_level = cls.get_user_kyc_level(user_id)
        regulatory_limits = cls.get_limits(kyc_level)

        # Get operational ceiling from WalletSystemConfig
        operational_config = WalletSystemConfig.get_config()

        # Apply restrictive precedence: min(regulatory, action-specific operational)
        # Operational ceilings are action-specific (deposit/withdraw/transfer); the
        # per-transaction regulatory limit must not be clamped by the transfer
        # ceiling alone (Issue H).
        operational_ceiling = cls._operational_per_txn_ceiling(operational_config, action)

        effective_per_txn = min(
            regulatory_limits['per_txn_limit'],
            operational_ceiling
        )

        action_map = {
            'send': 'can_send',
            'receive': 'can_receive',
            'withdraw': 'can_withdraw',
            'deposit': 'can_deposit'
        }

        allowed_attr = action_map.get(action)
        if not allowed_attr:
            return {'allowed': False, 'reason': f'Unknown action: {action}'}

        if not regulatory_limits.get(allowed_attr, False):
            return {
                'allowed': False,
                'reason': f'{action.capitalize()} not permitted at KYC level {regulatory_limits["label"]} (level {kyc_level}). Complete KYC verification to unlock.'
            }

        # Enforce WalletSystemConfig KYC requirement flags
        if action == 'deposit' and operational_config.require_kyc_for_deposits and kyc_level == 0:
            return {'allowed': False, 'reason': 'KYC verification required for deposits.'}
        if action == 'withdraw' and operational_config.require_kyc_for_withdrawals and kyc_level == 0:
            return {'allowed': False, 'reason': 'KYC verification required for withdrawals.'}
        if action == 'send' and operational_config.require_kyc_for_transfers and kyc_level == 0:
            return {'allowed': False, 'reason': 'KYC verification required for transfers.'}

        if amount > effective_per_txn:
            return {
                'allowed': False,
                'reason': f'Per-transaction limit is {effective_per_txn:,.0f} {currency}. Amount: {amount:,.0f}'
            }

        return {'allowed': True, 'kyc_level': kyc_level}

    @classmethod
    def check_regulatory_cumulative_limits(
        cls,
        account_id,
        currency: str,
        amount: Decimal,
        kyc_level: int
    ) -> Dict[str, Any]:
        """
        Enforce regulatory KYC daily/monthly *cumulative* limits.

        This uses the RegulatoryVolumeCalculator which supports both
        calendar and rolling window modes based on active policy.
        Volume is derived from the ledger with proper eligibility filters:
        - DEBIT entries only
        - COMPLETED transactions only
        - Excludes reversals
        - Per-account and per-currency isolation

        Args:
            account_id: Account UUID (the canonical Alipay-model identifier).
            currency: Account currency.
            amount: Proposed transaction amount.
            kyc_level: The authoritative KYC/KYB tier controlling the limits.

        Returns:
            Dict with 'allowed' (bool) and 'reason' / 'limit_type' if blocked.
        """
        account = db.session.get(AccountModel, account_id)
        if not account:
            return {'allowed': False, 'reason': 'Account not found', 'limit_type': 'cumulative'}

        limits = cls.get_limits(kyc_level)
        daily_limit = limits.get('daily_limit') or Decimal('0')
        monthly_limit = limits.get('monthly_limit') or Decimal('0')
        if not daily_limit and not monthly_limit:
            return {'allowed': True}

        calculator = RegulatoryVolumeCalculator()

        if daily_limit:
            allowed, current_volume, limit = calculator.check_daily_limit(
                account_id, currency, amount, daily_limit
            )
            if not allowed:
                return {
                    'allowed': False,
                    'limit_type': 'daily',
                    'reason': (
                        f'Daily regulatory limit ({limit:,.0f} {currency}) would be '
                        f'exceeded. Current volume: {current_volume:,.0f}, requested: {amount:,.0f}'
                    ),
                }

        if monthly_limit:
            allowed, current_volume, limit = calculator.check_monthly_limit(
                account_id, currency, amount, monthly_limit
            )
            if not allowed:
                return {
                    'allowed': False,
                    'limit_type': 'monthly',
                    'reason': (
                        f'Monthly regulatory limit ({limit:,.0f} {currency}) would be '
                        f'exceeded. Current volume: {current_volume:,.0f}, requested: {amount:,.0f}'
                    ),
                }

        return {'allowed': True}

    @classmethod
    def _check_org_transaction_allowed(
        cls,
        org,
        amount,
        action: str,
        currency: str,
        recipient_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Apply two-tier organisation KYB gating to a transaction."""
        from app.identity.services.organisation_kyb_service import OrganisationKYBService

        status = OrganisationKYBService.compute_status(org)
        pending_keys = [p["key"] for p in status["pending_requirements"]]

        # L1 (basic KYB) is required before the organisation can transact at all.
        if not status["is_operational_kyb"]:
            needs_license = "license" in pending_keys
            return {
                "allowed": False,
                "reason": (
                    "Complete your organisation KYB (business registration, identity and tax"
                    + (" and operating licence" if needs_license else "")
                    + ") before transacting."
                ),
                "kyb_required": "basic",
                "pending": pending_keys,
            }

        # L2 (full KYB incl. source of funds) only for personal transfers / large-value.
        if OrganisationKYBService.requires_full_kyb(org, amount, currency, recipient_user_id):
            if not status["is_full_kyb"]:
                return {
                    "allowed": False,
                    "reason": (
                        "This transaction requires full organisation KYB, including a verified "
                        "source of funds. Complete the remaining verification steps to proceed."
                    ),
                    "kyb_required": "full",
                    "pending": pending_keys,
                }

        # Passed KYB gates; apply standard amount/limit checks using the mapped level.
        kyc_level = status["kyb_level"]  # 1 (basic) or 2 (full)
        regulatory_limits = cls.get_limits(kyc_level)

        # Get operational ceiling from WalletSystemConfig
        operational_config = WalletSystemConfig.get_config()

        # Apply restrictive precedence: min(regulatory, action-specific operational)
        operational_ceiling = cls._operational_per_txn_ceiling(operational_config, action)
        effective_per_txn = min(
            regulatory_limits['per_txn_limit'],
            operational_ceiling
        )

        action_map = {
            'send': 'can_send',
            'receive': 'can_receive',
            'withdraw': 'can_withdraw',
            'deposit': 'can_deposit'
        }
        allowed_attr = action_map.get(action)
        if not allowed_attr:
            return {'allowed': False, 'reason': f'Unknown action: {action}'}
        if not regulatory_limits.get(allowed_attr, False):
            return {
                'allowed': False,
                'reason': f'{action.capitalize()} not permitted for this organisation KYB tier.'
            }
        if amount > effective_per_txn:
            return {
                'allowed': False,
                'reason': f'Per-transaction limit for this organisation KYB tier is {effective_per_txn:,.0f} {currency}. Amount: {amount:,.0f}'
            }
        return {'allowed': True, 'kyb_level': kyc_level}

    @classmethod
    def check_volume_limits(
        cls,
        account_id: str,
        amount: Decimal,
        currency: str,
        period: str = 'daily'
    ) -> Dict[str, Any]:
        """Check cumulative daily/monthly volume against regulatory KYC limits.

        Delegates to ``enforce_cumulative_volume`` (ledger-derived volume, no commit).
        """
        account = db.session.get(AccountModel, account_id)
        if not account:
            return {'allowed': False, 'reason': 'Account not found'}
        try:
            cls.enforce_cumulative_volume(int(account.user_id), account_id, amount, currency, period)
        except LimitExceededError:
            limit = cls.get_effective_cumulative_limit(int(account.user_id), currency, period)
            return {
                'allowed': False,
                'reason': f'{period.capitalize()} volume limit ({limit:,.0f} {currency}) exceeded.'
            }
        return {'allowed': True}

    @classmethod
    def get_effective_cumulative_limit(
        cls,
        user_id: int,
        currency: str,
        period: str
    ) -> Optional[Decimal]:
        """Return the effective cumulative (daily/monthly) limit for a user/org.

        Effective daily limit = restrictive minimum of the regulatory KYC daily limit
        and the operational daily ceiling from WalletSystemConfig.max_daily_amount.
        Falls back to Flask-config WALLET_DAILY_LIMIT_HOME/LOCAL for backward compatibility.
        
        Effective monthly limit = restrictive minimum of the regulatory KYC monthly limit
        and the operational monthly ceiling from WalletSystemConfig.max_monthly_amount.
        Returns None when the regulatory limit is zero/undefined (no cumulative cap).
        """
        from app.identity.models.organisation import Organisation
        from app.wallet.models.config import WalletSystemConfig

        org = db.session.get(Organisation, user_id)
        if org is not None and not getattr(org, "is_deleted", False):
            from app.identity.services.organisation_kyb_service import OrganisationKYBService
            status = OrganisationKYBService.compute_status(org)
            reg = cls.get_limits(status["kyb_level"])
        else:
            reg = cls.get_limits(cls.get_user_kyc_level(user_id))

        operational_config = WalletSystemConfig.get_config()

        if period == 'daily':
            regulatory = reg.get('daily_limit') or Decimal('0')
            # Use WalletSystemConfig operational daily ceiling, fallback to Flask config
            op = None
            if operational_config.max_daily_amount is not None:
                try:
                    op = Decimal(str(operational_config.max_daily_amount))
                except (ValueError, decimal.InvalidOperation):
                    op = None
            if op is None:
                op_key = 'WALLET_DAILY_LIMIT_HOME' if currency == 'USD' else 'WALLET_DAILY_LIMIT_LOCAL'
                op = current_app.config.get(op_key)
            if not regulatory:
                return None
            if op is None:
                return regulatory
            return min(regulatory, op)
        if period == 'monthly':
            regulatory = reg.get('monthly_limit') or Decimal('0')
            # Use WalletSystemConfig operational monthly ceiling
            op = None
            if operational_config.max_monthly_amount is not None:
                try:
                    op = Decimal(str(operational_config.max_monthly_amount))
                except (ValueError, decimal.InvalidOperation):
                    op = None
            if op is not None:
                if not regulatory:
                    return None
                return min(regulatory, op)
            if not regulatory:
                return None
            return regulatory
        return None

    @classmethod
    def enforce_cumulative_volume(
        cls,
        user_id: int,
        account_id,
        amount: Decimal,
        currency: str,
        period: str = 'daily'
    ) -> None:
        """Raise LimitExceededError if a cumulative limit would be exceeded.

        Volume is derived from the ledger (authoritative). Performs NO commit, so it
        is safe to call inside WalletService's atomic transaction block.
        """
        # Get the KYC level to determine regulatory limits
        from app.identity.models.organisation import Organisation
        org = db.session.get(Organisation, user_id)
        if org is not None and not getattr(org, "is_deleted", False):
            from app.identity.services.organisation_kyb_service import OrganisationKYBService
            status = OrganisationKYBService.compute_status(org)
            kyc_level = status["kyb_level"]
        else:
            kyc_level = cls.get_user_kyc_level(user_id)
        
        limits = cls.get_limits(kyc_level)
        
        if period == 'daily':
            daily_limit = limits.get('daily_limit') or Decimal('0')
            if not daily_limit:
                return
            calculator = RegulatoryVolumeCalculator()
            allowed, current_volume, limit = calculator.check_daily_limit(
                account_id, currency, amount, daily_limit
            )
            if not allowed:
                raise LimitExceededError(
                    limit_type=f"kyc_{period}",
                    currency=currency,
                    limit=float(limit),
                    current=float(current_volume)
                )
        else:
            monthly_limit = limits.get('monthly_limit') or Decimal('0')
            if not monthly_limit:
                return
            calculator = RegulatoryVolumeCalculator()
            allowed, current_volume, limit = calculator.check_monthly_limit(
                account_id, currency, amount, monthly_limit
            )
            if not allowed:
                raise LimitExceededError(
                    limit_type=f"kyc_{period}",
                    currency=currency,
                    limit=float(limit),
                    current=float(current_volume)
                )

    @classmethod
    def get_transaction_limits(cls, user_id: int, currency: str = 'UGX') -> Dict[str, Any]:
        """Get all applicable limits for a user.

        Per-transaction limits use restrictive precedence (regulatory MIN operational
        per-action ceiling from WalletSystemConfig).
        
        Effective daily limit = min(regulatory daily, operational daily ceiling).
        Currently the operational daily ceiling is sourced from Flask config 
        (WALLET_DAILY_LIMIT_HOME/LOCAL) as WalletSystemConfig does not yet have
        daily/monthly operational ceiling fields. This is a deferred enhancement
        (see BACKLOG.md). Monthly limit is purely regulatory (ledger-derived).
        """
        from app.identity.models.organisation import Organisation

        org = db.session.get(Organisation, user_id)
        if org is not None and not getattr(org, "is_deleted", False):
            from app.identity.services.organisation_kyb_service import OrganisationKYBService
            status = OrganisationKYBService.compute_status(org)
            kyc_level = status["kyb_level"]
        else:
            kyc_level = cls.get_user_kyc_level(user_id)

        regulatory_limits = cls.get_limits(kyc_level)
        operational_config = WalletSystemConfig.get_config()

        per_txn = {
            'deposit': min(regulatory_limits['per_txn_limit'], Decimal(str(operational_config.max_deposit_amount))),
            'withdraw': min(regulatory_limits['per_txn_limit'], Decimal(str(operational_config.max_withdrawal_amount))),
            'transfer': min(regulatory_limits['per_txn_limit'], Decimal(str(operational_config.max_transfer_amount))),
        }

        reg_daily = regulatory_limits['daily_limit']
        op_daily_key = 'WALLET_DAILY_LIMIT_HOME' if currency == 'USD' else 'WALLET_DAILY_LIMIT_LOCAL'
        op_daily = current_app.config.get(op_daily_key)
        effective_daily = min(reg_daily, Decimal(str(op_daily))) if op_daily is not None else reg_daily
        effective_monthly = regulatory_limits['monthly_limit']

        return {
            'kyc_level': kyc_level,
            'kyc_label': regulatory_limits['label'],
            'per_transaction': {k: float(v) for k, v in per_txn.items()},
            'per_transaction_limit': float(per_txn['transfer']),
            'daily_limit': float(effective_daily),
            'monthly_limit': float(effective_monthly),
            'max_balance': float(regulatory_limits.get('max_balance', 0)),
            'features': {
                'send': regulatory_limits['can_send'],
                'receive': regulatory_limits['can_receive'],
                'withdraw': regulatory_limits['can_withdraw'],
                'deposit': regulatory_limits['can_deposit']
            }
        }

