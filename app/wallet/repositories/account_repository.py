"""
app/wallet/repositories/account_repository.py
Account repository with atomic operations and proper locking.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from sqlalchemy import select, insert
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.extensions import db
from app.utils.id_validator import assert_internal_id
from app.wallet.models.ledger import AccountModel


class AccountRepository:
    """
    Repository for account database operations.
    
    All operations are atomic with proper locking to prevent race conditions.
    """

    def __init__(self, db_session: Session = None):
        self.db = db_session or db.session

    def get_by_id(
        self, 
        account_id: UUID, 
        for_update: bool = False
    ) -> Optional[AccountModel]:
        """
        Get account by ID.
        
        Args:
            account_id: Account UUID
            for_update: If True, locks row with SELECT FOR UPDATE
            
        Returns:
            AccountModel or None
        """
        query = select(AccountModel).where(AccountModel.id == account_id)
        
        if for_update:
            query = query.with_for_update()
        
        return self.db.execute(query).scalar_one_or_none()

    def get_by_user_id(
        self, 
        user_id: int, 
        currency: str = 'USD',
        for_update: bool = False
    ) -> Optional[AccountModel]:
        """
        Get account by user ID and currency.
        
        Args:
            user_id: User ID (must be BIGINT internal ID)
            currency: Currency code
            for_update: If True, locks row with SELECT FOR UPDATE
            
        Returns:
            AccountModel or None
            
        Raises:
            ValueError: If user_id is not a valid internal ID
        """
        validated_user_id = assert_internal_id(user_id)
        
        query = (
            select(AccountModel)
            .where(
                AccountModel.user_id == validated_user_id,
                AccountModel.currency == currency
            )
        )
        
        if for_update:
            query = query.with_for_update()
        
        return self.db.execute(query).scalar_one_or_none()

    def get_wallets_for_update(self, user_ids: List[int]) -> List[AccountModel]:
        """
        Get multiple wallets with row locks in consistent ID order.
        
        This prevents deadlocks by always locking in the same order.
        
        Args:
            user_ids: List of user IDs to lock
            
        Returns:
            List of AccountModel with locks held
        """
        # Sort IDs to ensure consistent locking order
        sorted_ids = sorted(user_ids)
        
        wallets = []
        for user_id in sorted_ids:
            wallet = self.get_by_user_id(user_id, for_update=True)
            if wallet:
                wallets.append(wallet)
        
        return wallets

    def get_or_create(
        self, 
        user_id: int, 
        currency: str = 'USD'
    ) -> AccountModel:
        """
        Get or create account atomically.
        
        Uses PostgreSQL ON CONFLICT to eliminate race conditions.
        
        Args:
            user_id: User ID
            currency: Currency code
            
        Returns:
            AccountModel (existing or newly created)
        """
        # Try to get existing first (with lock)
        existing = self.get_by_user_id(user_id, currency, for_update=True)
        if existing:
            return existing
        
        # Create new account using ON CONFLICT DO NOTHING
        stmt = pg_insert(AccountModel).values(
            user_id=user_id,
            currency=currency,
            is_frozen=False,
            daily_volume=0,
            monthly_volume=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ).on_conflict_do_nothing(
            index_elements=['user_id', 'currency']
        ).returning(AccountModel)
        
        result = self.db.execute(stmt)
        self.db.flush()
        
        # If insert succeeded, return the new account
        new_account = result.scalar_one_or_none()
        if new_account:
            return new_account
        
        # Another transaction created it - fetch it now
        return self.get_by_user_id(user_id, currency, for_update=True)

    def freeze_account(
        self, 
        account_id: UUID, 
        reason: str
    ) -> bool:
        """
        Freeze an account.
        
        Args:
            account_id: Account UUID
            reason: Reason for freezing
            
        Returns:
            True if frozen, False if not found
        """
        account = self.get_by_id(account_id, for_update=True)
        if not account:
            return False
        
        account.is_frozen = True
        account.frozen_reason = reason
        account.frozen_at = datetime.utcnow()
        
        return True

    def unfreeze_account(self, account_id: UUID) -> bool:
        """
        Unfreeze an account.
        
        Args:
            account_id: Account UUID
            
        Returns:
            True if unfrozen, False if not found
        """
        account = self.get_by_id(account_id, for_update=True)
        if not account:
            return False
        
        account.is_frozen = False
        account.frozen_reason = None
        account.frozen_at = None
        
        return True

    def reset_daily_volume(self, account_id: UUID) -> bool:
        """
        Reset daily volume counter.
        
        Args:
            account_id: Account UUID
            
        Returns:
            True if reset, False if not found
        """
        account = self.get_by_id(account_id, for_update=True)
        if not account:
            return False
        
        account.daily_volume = 0
        account.daily_volume_reset_at = datetime.utcnow()
        
        return True

    def reset_monthly_volume(self, account_id: UUID) -> bool:
        """
        Reset monthly volume counter.
        
        Args:
            account_id: Account UUID
            
        Returns:
            True if reset, False if not found
        """
        account = self.get_by_id(account_id, for_update=True)
        if not account:
            return False
        
        account.monthly_volume = 0
        account.monthly_volume_reset_at = datetime.utcnow()
        
        return True

    def update_volume(
        self,
        account_id: UUID,
        amount: float,
        volume_type: str = 'daily'
    ) -> bool:
        """
        Update volume counter.
        
        Args:
            account_id: Account UUID
            amount: Amount to add to volume
            volume_type: 'daily' or 'monthly'
            
        Returns:
            True if updated, False if not found
        """
        account = self.get_by_id(account_id, for_update=True)
        if not account:
            return False
        
        if volume_type == 'daily':
            account.daily_volume += amount
        elif volume_type == 'monthly':
            account.monthly_volume += amount
        
        return True
