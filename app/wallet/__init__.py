"""
app/wallet/__init__.py
Main wallet module exports - optimized for lazy loading.
"""

# Exceptions are lightweight, safe to keep here
from app.wallet.exceptions import (
    WalletError,
    WalletNotFoundError,
    InsufficientBalanceError,
    DuplicateTransactionError,
    UnsupportedCurrencyError,
    LimitExceededError,
    WalletFrozenError,
    ConversionError,
)

# Core service getters (Lazy)
def get_wallet_service():
    from app.wallet.services.wallet_service import WalletService
    return WalletService()

def get_currency_service():
    from app.wallet.services.currency_service import CurrencyService
    return CurrencyService()

def get_commission_service():
    from app.wallet.services.commission_service import CommissionService
    return CommissionService()

def get_payout_service():
    from app.wallet.services.payout_service import PayoutService
    return PayoutService()

# Convenience functions (Lazy)
def get_wallet(user_id: int):
    from app.wallet.repositories.wallet_repository import WalletRepository
    repo = WalletRepository()
    return repo.get_by_user_id(user_id)

def get_or_create_wallet(user_id: int):
    from app.wallet.repositories.wallet_repository import WalletRepository
    repo = WalletRepository()
    return repo.get_or_create_by_user_id(user_id)

def get_agent_commission_total(agent_id: int) -> float:
    from app.wallet.services.commission_service import CommissionService
    service = CommissionService()
    return float(service.get_agent_total(agent_id))

def get_agent_commissions(agent_id: int):
    from app.wallet.services.commission_service import CommissionService
    service = CommissionService()
    return service.get_agent_commissions(agent_id)

def log_agent_commission(agent_id: int, amount, source, tx_type):
    from decimal import Decimal
    from app.wallet.services.commission_service import CommissionService
    service = CommissionService()
    return service.record_commission(
        agent_id=agent_id,
        amount=Decimal(str(amount)),
        currency="UGX",
        source_type=tx_type,
        source_id=source,
    )

def create_payout_request(agent_id, amount, method="bank", details=None):
    from decimal import Decimal
    from app.wallet.services.payout_service import PayoutService
    service = PayoutService()
    return service.create_request(agent_id, Decimal(str(amount)), "UGX", method, details or {})

def list_payout_requests(filter_status=None):
    from app.wallet.services.payout_service import PayoutService
    service = PayoutService()
    return service.list_requests(status=filter_status)

def update_payout_status(req_id, status, processor=None, notes=None):
    from app.wallet.services.payout_service import PayoutService
    service = PayoutService()
    if status == "approved":
        return service.approve_request(req_id, processor, notes)
    elif status == "rejected":
        return service.reject_request(req_id, processor, notes)
    elif status == "paid":
        return service.mark_as_paid(req_id, processor, notes)
    return False

# Blueprints - imported on demand or via specific paths to avoid loading the whole module
# These are kept for backward compatibility but moving them to the bottom
# helps avoid circular issues during lazy loads.
def get_wallet_api_bp():
    from app.wallet.api.wallet_api import wallet_api_bp
    return wallet_api_bp

def get_admin_wallet_bp():
    from app.wallet.api.admin_api import admin_wallet_bp
    return admin_wallet_bp
