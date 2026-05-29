# app/wallet/services/wallet_status_service.py
"""
Wallet Status Service - Checks wallet existence and tier-based feature access
"""
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from flask import current_app
from flask_login import current_user


class WalletFeature(Enum):
    """Wallet features that can be gated"""
    # Basic features (always visible)
    VIEW_DASHBOARD = "view_dashboard"
    VIEW_TERMS = "view_terms"

    # Features requiring wallet (any tier)
    MAKE_DEPOSIT = "make_deposit"
    VIEW_TRANSACTIONS = "view_transactions"
    VIEW_FX_RATES = "view_fx_rates"
    VIEW_COMPLIANCE = "view_compliance"

    # Features requiring verified wallet + tier
    SEND_MONEY = "send_money"
    RECEIVE_MONEY = "receive_money"
    WITHDRAW_MONEY = "withdraw_money"
    CREATE_PAYOUT = "create_payout"
    VIEW_PAYOUT_HISTORY = "view_payout_history"
    VIEW_COMMISSIONS = "view_commissions"

    # Premium features (higher tiers)
    INTERNATIONAL_TRANSFER = "international_transfer"
    BULK_PAYMENT = "bulk_payment"
    MERCHANT_ACCOUNT = "merchant_account"
    API_ACCESS = "api_access"


class WalletTier(Enum):
    """Wallet access tiers based on status and KYC"""
    NO_WALLET = 0  # No wallet created
    PENDING_ACTIVATION = 1  # Wallet created but not activated
    TIER_0_BASIC = 2  # Activated, basic KYC
    TIER_1_VERIFIED = 3  # ID verified
    TIER_2_ENHANCED = 4  # Enhanced KYC
    TIER_3_FULL = 5  # Full KYC


@dataclass
class WalletStatus:
    """Complete wallet status for a user"""
    exists: bool
    is_activated: bool
    tier: WalletTier
    kyc_level: int
    can_deposit: bool
    can_withdraw: bool
    can_send: bool
    can_receive: bool
    can_request_payout: bool
    can_view_commissions: bool
    requires_activation: bool
    requires_kyc: bool
    requires_pin_setup: bool
    requires_terms_acceptance: bool
    missing_requirements: List[str]
    feature_access: Dict[WalletFeature, bool]


class WalletStatusService:
    """Service to check wallet status and feature access"""

    @classmethod
    def get_wallet_status(cls, user, owner_type=None) -> WalletStatus:
        """Get complete wallet status for a user or organisation (g-cached per request).
        
        Args:
            user: User object or organisation id (for organisations)
            owner_type: AccountOwnerType (USER or ORGANISATION). If None, auto-detects.
        """
        from app.wallet.models.ledger import AccountModel, AccountOwnerType
        _g_cache = None
        _g_key = f'_wallet_status_{getattr(user, "id", user)}_{owner_type}'
        try:
            from flask import g as _g
            if not hasattr(_g, '_wallet_status_cache'):
                _g._wallet_status_cache = {}
            if _g_key in _g._wallet_status_cache:
                return _g._wallet_status_cache[_g_key]
            _g_cache = _g._wallet_status_cache
        except RuntimeError:
            pass  # Outside request context

        # Auto-detect owner type if not provided
        if owner_type is None:
            # Check if it's a User object (has email attribute)
            if hasattr(user, 'email'):
                owner_type = AccountOwnerType.USER
            else:
                # Assume it's an organisation id
                owner_type = AccountOwnerType.ORGANISATION

        # Get the owner ID
        if owner_type == AccountOwnerType.USER:
            owner_id = user.id
            user_kyc_level = getattr(user, 'kyc_level', 0)
            has_pin = bool(getattr(user, 'transaction_pin_hash', None))
            # For organisations, check verification_status instead of kyc_level
            org_verification_status = None
        else:
            # For organisations, user is the organisation id
            owner_id = user if isinstance(user, int) else int(user)
            # Load organisation to get verification status
            from app.identity.models.organisation import Organisation
            org = Organisation.query.get(owner_id)
            if org:
                org_verification_status = org.verification_status
                # Map verification status to KYC level equivalent
                if org_verification_status == 'verified':
                    user_kyc_level = 2  # Treat verified org as Tier 2
                elif org_verification_status == 'pending':
                    user_kyc_level = 1  # Treat pending org as Tier 1
                else:
                    user_kyc_level = 0
                has_pin = True  # Organisations don't use PIN
            else:
                user_kyc_level = 0
                has_pin = False
                org_verification_status = 'unverified'

        # Check if owner has wallet
        account = AccountModel.query.filter_by(
            user_id=owner_id,
            owner_type=owner_type
        ).first()

        if not account:
            _no_wallet = WalletStatus(
                exists=False,
                is_activated=False,
                tier=WalletTier.NO_WALLET,
                kyc_level=user_kyc_level,
                can_deposit=False,
                can_withdraw=False,
                can_send=False,
                can_receive=False,
                can_request_payout=False,
                can_view_commissions=False,
                requires_activation=False,
                requires_kyc=True,
                requires_pin_setup=True,
                requires_terms_acceptance=True,
                missing_requirements=['Create a wallet first'],
                feature_access=cls._get_feature_access(False, False, 0)
            )
            if _g_cache is not None:
                _g_cache[_g_key] = _no_wallet
            return _no_wallet

        # Determine tier based on activation and KYC/verification
        is_activated = account.verified

        if not is_activated:
            tier = WalletTier.PENDING_ACTIVATION
        elif user_kyc_level >= 3:
            tier = WalletTier.TIER_3_FULL
        elif user_kyc_level >= 2:
            tier = WalletTier.TIER_2_ENHANCED
        elif user_kyc_level >= 1:
            tier = WalletTier.TIER_1_VERIFIED
        else:
            tier = WalletTier.TIER_0_BASIC

        # Check requirements
        missing = []
        if not is_activated:
            missing.append('Activate your wallet')
        if not has_pin and owner_type == AccountOwnerType.USER:
            missing.append('Set transaction PIN')
        if user_kyc_level == 0 and tier != WalletTier.PENDING_ACTIVATION:
            if owner_type == AccountOwnerType.USER:
                missing.append('Complete KYC verification')
            else:
                missing.append('Complete organisation verification')

        # Determine feature access
        can_send = is_activated and user_kyc_level >= 1
        can_withdraw = is_activated and user_kyc_level >= 1
        can_receive = is_activated  # Everyone with activated wallet can receive
        can_deposit = is_activated
        can_request_payout = is_activated and user_kyc_level >= 1
        can_view_commissions = is_activated and user_kyc_level >= 1

        # Get feature access map
        feature_access = cls._get_feature_access(is_activated, can_send, user_kyc_level)

        _result = WalletStatus(
            exists=True,
            is_activated=is_activated,
            tier=tier,
            kyc_level=user_kyc_level,
            can_deposit=can_deposit,
            can_withdraw=can_withdraw,
            can_send=can_send,
            can_receive=can_receive,
            can_request_payout=can_request_payout,
            can_view_commissions=can_view_commissions,
            requires_activation=not is_activated,
            requires_kyc=user_kyc_level == 0,
            requires_pin_setup=not has_pin,
            requires_terms_acceptance=not account.terms_accepted_at,
            missing_requirements=missing,
            feature_access=feature_access
        )
        if _g_cache is not None:
            _g_cache[_g_key] = _result
        return _result

    @classmethod
    def _get_feature_access(cls, is_activated: bool, can_send: bool, kyc_level: int) -> Dict[WalletFeature, bool]:
        """Get feature access mapping"""
        base_access = {
            WalletFeature.VIEW_DASHBOARD: True,
            WalletFeature.VIEW_TERMS: True,
            WalletFeature.MAKE_DEPOSIT: is_activated,
            WalletFeature.VIEW_TRANSACTIONS: is_activated,
            WalletFeature.VIEW_FX_RATES: is_activated,
            WalletFeature.VIEW_COMPLIANCE: is_activated,
            WalletFeature.SEND_MONEY: can_send,
            WalletFeature.RECEIVE_MONEY: is_activated,
            WalletFeature.WITHDRAW_MONEY: can_send,
            WalletFeature.CREATE_PAYOUT: can_send,
            WalletFeature.VIEW_PAYOUT_HISTORY: can_send,
            WalletFeature.VIEW_COMMISSIONS: can_send,
            WalletFeature.INTERNATIONAL_TRANSFER: kyc_level >= 2,
            WalletFeature.BULK_PAYMENT: kyc_level >= 3,
            WalletFeature.MERCHANT_ACCOUNT: kyc_level >= 2,
            WalletFeature.API_ACCESS: kyc_level >= 2,
        }
        return base_access

    @classmethod
    def can_access_feature(cls, user, feature: WalletFeature) -> bool:
        """Check if user can access a specific feature"""
        status = cls.get_wallet_status(user)
        return status.feature_access.get(feature, False)

    @classmethod
    def get_visible_sidebar_items(cls, user) -> List[Dict]:
        """Get sidebar items based on wallet status"""
        status = cls.get_wallet_status(user)

        # Base items always visible
        items = [
            {"name": "Dashboard", "url": "wallet.wallet_dashboard", "icon": "fa-gauge-high",
             "feature": WalletFeature.VIEW_DASHBOARD},
        ]

        # Wallet core items (require wallet)
        if status.exists:
            items.extend([
                {"name": "Deposit Funds", "url": "wallet.deposit_page", "icon": "fa-arrow-down",
                 "feature": WalletFeature.MAKE_DEPOSIT},
                {"name": "Send Funds", "url": "wallet.send_page", "icon": "fa-paper-plane",
                 "feature": WalletFeature.SEND_MONEY},
                {"name": "Withdraw Funds", "url": "wallet.withdraw_page", "icon": "fa-arrow-up",
                 "feature": WalletFeature.WITHDRAW_MONEY},
                {"name": "Transaction History", "url": "wallet.wallet_transactions", "icon": "fa-list",
                 "feature": WalletFeature.VIEW_TRANSACTIONS},
                {"name": "FX Rates", "url": "wallet.fx_rates", "icon": "fa-exchange-alt",
                 "feature": WalletFeature.VIEW_FX_RATES},
            ])
        else:
            # No wallet - show create wallet link
            items.append(
                {"name": "Create Wallet", "url": "wallet.wallet_create_page", "icon": "fa-wallet", "feature": None})

        # Agent/Payout items (require wallet + KYC)
        if status.exists and status.can_view_commissions:
            items.extend([
                {"name": "Agent Payout", "url": "wallet.agent_payout_history", "icon": "fa-coins",
                 "feature": WalletFeature.VIEW_PAYOUT_HISTORY},
            ])

        # Account items (always visible)
        items.extend([
            {"name": "Compliance", "url": "wallet.compliance_status", "icon": "fa-shield-alt",
             "feature": WalletFeature.VIEW_COMPLIANCE},
            {"name": "Settings", "url": "wallet.wallet_settings", "icon": "fa-cog", "feature": None},
            {"name": "Terms & Conditions", "url": "wallet.wallet_terms", "icon": "fa-file-contract",
             "feature": WalletFeature.VIEW_TERMS},
        ])

        return items

    @classmethod
    def get_action_buttons(cls, user) -> List[Dict]:
        """Get conditional action buttons based on wallet status"""
        status = cls.get_wallet_status(user)

        buttons = []

        if not status.exists:
            buttons.append({
                "name": "Create Wallet",
                "url": "wallet.wallet_create_page",
                "color": "primary",
                "icon": "fa-wallet",
                "order": 1
            })
        elif status.requires_activation:
            buttons.append({
                "name": "Activate Wallet",
                "url": "wallet.wallet_activate",
                "color": "warning",
                "icon": "fa-check-circle",
                "order": 1
            })
        else:
            buttons.append({
                "name": "Deposit",
                "url": "wallet.deposit_page",
                "color": "success",
                "icon": "fa-arrow-down",
                "order": 1
            })
            if status.can_send:
                buttons.append({
                    "name": "Send",
                    "url": "wallet.send_page",
                    "color": "primary",
                    "icon": "fa-paper-plane",
                    "order": 2
                })
            if status.can_withdraw:
                buttons.append({
                    "name": "Withdraw",
                    "url": "wallet.withdraw_page",
                    "color": "danger",
                    "icon": "fa-arrow-up",
                    "order": 3
                })

        return buttons

    @classmethod
    def get_wallet_banner(cls, user) -> Optional[Dict]:
        """Get banner message based on wallet status"""
        status = cls.get_wallet_status(user)

        if not status.exists:
            return {
                "type": "info",
                "title": "Create Your Wallet",
                "message": "You don't have a wallet yet. Create one to start sending and receiving money.",
                "action": "Create Wallet",
                "action_url": "wallet.wallet_create_page"
            }
        elif status.requires_activation:
            return {
                "type": "warning",
                "title": "Wallet Not Activated",
                "message": "Your wallet has been created but needs activation. Please complete the activation process.",
                "action": "Activate Now",
                "action_url": "wallet.wallet_activate"
            }
        elif status.requires_kyc:
            remaining = status.missing_requirements
            return {
                "type": "warning",
                "title": "KYC Verification Required",
                "message": f"Complete KYC verification to unlock full features. Required: {', '.join(remaining)}",
                "action": "Verify Now",
                "action_url": "/kyc/verify"
            }
        elif status.requires_pin_setup:
            return {
                "type": "info",
                "title": "Set Transaction PIN",
                "message": "Set a transaction PIN to secure your transfers and withdrawals.",
                "action": "Set PIN",
                "action_url": "wallet.pin_page"
            }

        return None
