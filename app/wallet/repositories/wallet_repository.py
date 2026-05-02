"""
app/wallet/repositories/wallet_repository.py
Wallet repository - thin wrapper around account_repository for compatibility.
"""

from typing import Optional, Dict, Any
from uuid import UUID
from app.wallet.repositories.account_repository import AccountRepository
from app.wallet.repositories.ledger_repository import LedgerRepository
from app.wallet.models.ledger import AccountModel


class WalletRepository:
    """
    Repository for wallet operations.
    
    This is a thin wrapper around AccountRepository for backward compatibility.
    The actual implementation uses the new account/ledger architecture.
    """

    def __init__(self, db_session=None):
        from app.extensions import db
        self.db = db_session or db.session
        self.account_repo = AccountRepository(self.db)
        self.ledger_repo = LedgerRepository(self.db)

    def get_by_user_id(
        self, 
        user_id: int, 
        for_update: bool = False
    ) -> Optional[AccountModel]:
        """
        Get wallet by user ID.
        
        Args:
            user_id: User ID
            for_update: If True, locks row with SELECT FOR UPDATE
            
        Returns:
            AccountModel or None
        """
        return self.account_repo.get_by_user_id(user_id, for_update=for_update)

    def get_or_create_by_user_id(
        self, 
        user_id: int
    ) -> AccountModel:
        """
        Get or create wallet for user.
        
        Args:
            user_id: User ID
            
        Returns:
            AccountModel (existing or newly created)
        """
        return self.account_repo.get_or_create(user_id)

    def get_balance(
        self, 
        user_id: int, 
        currency: str = 'USD'
    ) -> Dict[str, Any]:
        """
        Get wallet balance derived from ledger.
        
        Args:
            user_id: User ID
            currency: Currency code
            
        Returns:
            Dict with balance information
        """
        account = self.account_repo.get_by_user_id(user_id)
        
        if not account:
            return {
                "exists": False,
                "balance": "0.00",
                "currency": currency,
                "is_frozen": False
            }
        
        balance = self.ledger_repo.get_balance(account.id, currency)
        
        return {
            "exists": True,
            "account_id": str(account.id),
            "user_id": user_id,
            "balance": str(balance),
            "currency": currency,
            "is_frozen": account.is_frozen,
            "frozen_reason": account.frozen_reason,
            "updated_at": account.updated_at.isoformat() if account.updated_at else None
        }

    def check_frozen(self, user_id: int) -> bool:
        """
        Check if wallet is frozen.
        
        Args:
            user_id: User ID
            
        Returns:
            True if frozen, False otherwise
        """
        account = self.account_repo.get_by_user_id(user_id)
        return account.is_frozen if account else False

    def get_frozen_reason(self, user_id: int) -> Optional[str]:
        """
        Get reason wallet is frozen.
        
        Args:
            user_id: User ID
            
        Returns:
            Frozen reason or None
        """
        account = self.account_repo.get_by_user_id(user_id)
        return account.frozen_reason if account else None

    # DEPRECATED: update_balance() removed - use ledger entries instead
    def update_balance(self, *args, **kwargs):
        """
        DEPRECATED: Balance updates are done via ledger entries.
        This method is kept for compatibility but raises an error.
        """
        raise NotImplementedError(
            "update_balance() is deprecated. Use ledger_repository.post_entries() instead."
        )
