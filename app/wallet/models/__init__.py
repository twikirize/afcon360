"""
app/wallet/models/__init__.py
Financial-grade wallet models with double-entry ledger architecture.

TERMINOLOGY (CRITICAL):
  System User Account = User (app/identity/models/user.py)
                        - Core platform identity
                        - Internal ID: user.id (BIGINT) - DB relations only
                        - External ID: user.public_id (UUID) - URLs/APIs

  Financial Account = AccountModel (app/wallet/models/ledger.py)
                      - Money/ledger account
                      - Each User may have ONE AccountModel (via User.wallet relationship)
                      - AccountOwnerType can be USER, ORGANISATION, PLATFORM, or SYSTEM

  Relationship:
    User (System User Account)
        │
        ├── optional financial relationship
        ▼
    AccountModel (Financial Account)
        │
        ▼
      LEDGER (via LedgerEntryModel)

RULE: NEVER confuse User with AccountModel. They are conceptually different.
      User.is_verified ≠ AccountModel.verified
      User.kyc_level ≠ AccountModel KYC requirements

New ledger-based models are exported here.
Legacy models remain in legacy_models.py for existing services to import directly.
"""

# New ledger-based models
from .ledger import LedgerEntryModel, AccountModel
from .transaction import TransactionModel
from .audit import AuditLogModel
from .fx import FXRateModel, FXTransactionModel
from .commission import AgentCommission
from .payout import PayoutRequest
from .adjustment import AdjustmentRequestModel
from .payment_method import PaymentMethodConfig, EventPaymentPreference
from .creation_tracker import WalletCreationEventModel
from .regulatory_volume import (
    WindowMode,
    RegulatoryVolumePolicy,
    RegulatoryVolumePolicyChangeRequest,
    LedgerReversalReference
)
from .agent_onboarding import AgentOnboarding, AgentOnboardingApproval
from .agent_float import AgentFloatAccount, AgentFloatLedger

__all__ = [
    'LedgerEntryModel',
    'AccountModel',
    'TransactionModel',
    'AuditLogModel',
    'FXRateModel',
    'FXTransactionModel',
    'AgentCommission',
    'PayoutRequest',
    'AdjustmentRequestModel',
    'PaymentMethodConfig',
    'EventPaymentPreference',
    'WalletCreationEventModel',
    'WindowMode',
    'RegulatoryVolumePolicy',
    'RegulatoryVolumePolicyChangeRequest',
    'LedgerReversalReference',
    'AgentOnboarding',
    'AgentOnboardingApproval',
    'AgentFloatAccount',
    'AgentFloatLedger',
]
