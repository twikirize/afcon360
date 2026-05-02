"""
app/wallet/repositories/ledger_repository.py
Double-entry ledger repository - the source of truth for all balances.
"""

from decimal import Decimal
from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta
from uuid import UUID
from sqlalchemy import select, func, and_, desc
from sqlalchemy.orm import Session
from app.extensions import db
from app.wallet.models.ledger import LedgerEntryModel, AccountModel, EntryType


class LedgerRepository:
    """
    Repository for ledger operations.
    
    All balance queries are derived from ledger_entries - never stored.
    """

    def __init__(self, db_session: Session = None):
        self.db = db_session or db.session

    def post_entries(self, entries: List[LedgerEntryModel]) -> None:
        """
        Post ledger entries within the caller's transaction.
        
        This method DOES NOT commit - it only adds entries to the session.
        The caller is responsible for transaction boundaries.
        
        Args:
            entries: List of LedgerEntryModel to insert
        """
        for entry in entries:
            self.db.add(entry)

    def get_balance(
        self, 
        account_id: UUID, 
        currency: str,
        as_of: Optional[datetime] = None
    ) -> Decimal:
        """
        Calculate balance from ledger entries.
        
        Balance = SUM(CREDIT) - SUM(DEBIT)
        
        Args:
            account_id: The account UUID
            currency: Currency code
            as_of: Optional timestamp to calculate balance as of a specific time
            
        Returns:
            Decimal balance (can be negative for liability accounts)
        """
        credit_sum = func.coalesce(
            func.sum(
                func.case(
                    (LedgerEntryModel.entry_type == EntryType.CREDIT, LedgerEntryModel.amount),
                    else_=Decimal('0')
                )
            ),
            Decimal('0')
        )
        
        debit_sum = func.coalesce(
            func.sum(
                func.case(
                    (LedgerEntryModel.entry_type == EntryType.DEBIT, LedgerEntryModel.amount),
                    else_=Decimal('0')
                )
            ),
            Decimal('0')
        )

        query = select(credit_sum - debit_sum).where(
            and_(
                LedgerEntryModel.account_id == account_id,
                LedgerEntryModel.currency == currency
            )
        )
        
        if as_of:
            query = query.where(LedgerEntryModel.created_at <= as_of)

        result = self.db.execute(query).scalar()
        return result or Decimal('0')

    def get_balances(self, account_id: UUID) -> Dict[str, Decimal]:
        """
        Get all currency balances for an account.
        
        Returns:
            Dict mapping currency codes to balances
        """
        query = (
            select(
                LedgerEntryModel.currency,
                func.sum(
                    func.case(
                        (LedgerEntryModel.entry_type == EntryType.CREDIT, LedgerEntryModel.amount),
                        else_=-LedgerEntryModel.amount
                    )
                ).label('balance')
            )
            .where(LedgerEntryModel.account_id == account_id)
            .group_by(LedgerEntryModel.currency)
        )
        
        results = self.db.execute(query).all()
        return {row.currency: row.balance or Decimal('0') for row in results}

    def get_daily_volume(
        self,
        account_id: UUID,
        currency: str,
        since: Optional[datetime] = None
    ) -> Decimal:
        """
        Get total outgoing volume (debits) for an account in a currency.
        
        Args:
            account_id: Account UUID
            currency: Currency code
            since: Start time (defaults to 24 hours ago)
            
        Returns:
            Decimal volume amount
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=1)

        query = select(
            func.coalesce(func.sum(LedgerEntryModel.amount), Decimal('0'))
        ).where(
            and_(
                LedgerEntryModel.account_id == account_id,
                LedgerEntryModel.currency == currency,
                LedgerEntryModel.entry_type == EntryType.DEBIT,
                LedgerEntryModel.created_at >= since
            )
        )

        result = self.db.execute(query).scalar()
        return result or Decimal('0')

    def get_monthly_volume(
        self,
        account_id: UUID,
        currency: str,
        since: Optional[datetime] = None
    ) -> Decimal:
        """
        Get total outgoing volume for the past 30 days.
        
        Args:
            account_id: Account UUID
            currency: Currency code
            since: Start time (defaults to 30 days ago)
            
        Returns:
            Decimal volume amount
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=30)

        query = select(
            func.coalesce(func.sum(LedgerEntryModel.amount), Decimal('0'))
        ).where(
            and_(
                LedgerEntryModel.account_id == account_id,
                LedgerEntryModel.currency == currency,
                LedgerEntryModel.entry_type == EntryType.DEBIT,
                LedgerEntryModel.created_at >= since
            )
        )

        result = self.db.execute(query).scalar()
        return result or Decimal('0')

    def get_entries_for_transaction(
        self,
        transaction_id: UUID,
        limit: int = 100
    ) -> List[LedgerEntryModel]:
        """
        Get all ledger entries for a specific transaction.
        
        Args:
            transaction_id: Transaction UUID
            limit: Maximum entries to return
            
        Returns:
            List of LedgerEntryModel
        """
        query = (
            select(LedgerEntryModel)
            .where(LedgerEntryModel.transaction_id == transaction_id)
            .order_by(desc(LedgerEntryModel.created_at))
            .limit(limit)
        )
        
        return self.db.execute(query).scalars().all()

    def get_account_ledger_history(
        self,
        account_id: UUID,
        currency: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[LedgerEntryModel]:
        """
        Get ledger history for an account.
        
        Args:
            account_id: Account UUID
            currency: Optional currency filter
            limit: Maximum entries
            offset: Pagination offset
            
        Returns:
            List of LedgerEntryModel ordered by created_at DESC
        """
        query = select(LedgerEntryModel).where(
            LedgerEntryModel.account_id == account_id
        )
        
        if currency:
            query = query.where(LedgerEntryModel.currency == currency)
        
        query = (
            query.order_by(desc(LedgerEntryModel.created_at))
            .offset(offset)
            .limit(limit)
        )
        
        return self.db.execute(query).scalars().all()

    def validate_account_balance(
        self,
        account_id: UUID,
        currency: str,
        required_amount: Decimal
    ) -> bool:
        """
        Check if account has sufficient balance.
        
        Args:
            account_id: Account UUID
            currency: Currency code
            required_amount: Amount needed
            
        Returns:
            True if balance >= required_amount
        """
        balance = self.get_balance(account_id, currency)
        return balance >= required_amount
