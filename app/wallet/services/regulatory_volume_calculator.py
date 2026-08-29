"""
app/wallet/services/regulatory_volume_calculator.py
Regulatory Volume Calculation Engine

Supports both calendar and rolling window modes with proper timezone handling.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Tuple
from uuid import UUID
from sqlalchemy import select, func, and_, case, not_, exists, ColumnElement
from sqlalchemy.orm import Session

from app.extensions import db
from app.wallet.models.ledger import LedgerEntryModel, AccountModel, EntryType
from app.wallet.models.transaction import TransactionModel, TransactionStatus
from app.wallet.models.regulatory_volume import (
    WindowMode,
    RegulatoryVolumePolicy,
    LedgerReversalReference,
)


class TimezoneEngine:
    """Handles timezone conversions for calendar boundary calculations."""
    
    KAMPALA_TZ_OFFSET = timedelta(hours=3)  # EAT = UTC+3
    
    @classmethod
    def utc_to_kampala(cls, utc_dt: datetime) -> datetime:
        """Convert UTC datetime to Kampala local time."""
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        return utc_dt.astimezone(timezone(cls.KAMPALA_TZ_OFFSET))
    
    @classmethod
    def kampala_to_utc(cls, kampala_dt: datetime) -> datetime:
        """Convert Kampala local time to UTC."""
        if kampala_dt.tzinfo is None:
            kampala_dt = kampala_dt.replace(tzinfo=timezone(cls.KAMPALA_TZ_OFFSET))
        return kampala_dt.astimezone(timezone.utc)
    
    @classmethod
    def get_kampala_now(cls) -> datetime:
        """Get current time in Kampala timezone."""
        return cls.utc_to_kampala(datetime.now(timezone.utc))
    
    @classmethod
    def get_day_start_utc(cls, kampala_dt: Optional[datetime] = None) -> datetime:
        """Get start of day (00:00:00) in Kampala, returned as UTC."""
        if kampala_dt is None:
            kampala_dt = cls.get_kampala_now()
        elif kampala_dt.tzinfo is None:
            kampala_dt = kampala_dt.replace(tzinfo=timezone(cls.KAMPALA_TZ_OFFSET))
        else:
            kampala_dt = kampala_dt.astimezone(timezone(cls.KAMPALA_TZ_OFFSET))
        
        day_start = kampala_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return day_start.astimezone(timezone.utc)
    
    @classmethod
    def get_month_start_utc(cls, kampala_dt: Optional[datetime] = None) -> datetime:
        """Get start of month (1st 00:00:00) in Kampala, returned as UTC."""
        if kampala_dt is None:
            kampala_dt = cls.get_kampala_now()
        elif kampala_dt.tzinfo is None:
            kampala_dt = kampala_dt.replace(tzinfo=timezone(cls.KAMPALA_TZ_OFFSET))
        else:
            kampala_dt = kampala_dt.astimezone(timezone(cls.KAMPALA_TZ_OFFSET))
        
        month_start = kampala_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return month_start.astimezone(timezone.utc)


class VolumeWindowCalculator:
    """
    Calculates the time window boundaries for regulatory volume queries.
    
    Supports both CALENDAR and ROLLING modes for daily and monthly windows.
    """
    
    def __init__(self, policy: Optional[RegulatoryVolumePolicy] = None):
        self.policy = policy or RegulatoryVolumePolicy.get_active_or_default()
    
    def get_daily_window_bounds(self, as_of: Optional[datetime] = None) -> Tuple[datetime, datetime]:
        """
        Get the UTC bounds for the daily volume window.
        
        Returns:
            (window_start_utc, window_end_utc) where end is the current time or as_of
        """
        end_time = as_of or datetime.now(timezone.utc)
        
        if self.policy.daily_window_mode is WindowMode.CALENDAR:
            # Calendar day: 00:00:00 local time to now
            window_start = TimezoneEngine.get_day_start_utc(end_time)
        else:
            # Rolling 24 hours
            window_start = end_time - timedelta(days=1)
        
        return (window_start, end_time)
    
    def get_monthly_window_bounds(self, as_of: Optional[datetime] = None) -> Tuple[datetime, datetime]:
        """
        Get the UTC bounds for the monthly volume window.
        
        Returns:
            (window_start_utc, window_end_utc) where end is the current time or as_of
        """
        end_time = as_of or datetime.now(timezone.utc)
        
        if self.policy.monthly_window_mode is WindowMode.CALENDAR:
            # Calendar month: 1st day 00:00:00 local time to now
            window_start = TimezoneEngine.get_month_start_utc(end_time)
        else:
            # Rolling 30 days
            window_start = end_time - timedelta(days=30)
        
        return (window_start, end_time)


class RegulatoryVolumeCalculator:
    """
    Canonical interface for calculating regulatory transaction volumes.
    
    This is the single entry point for KYC limit enforcement and other
    regulatory volume queries. It abstracts the window mode (calendar/rolling)
    and applies all eligibility filters.
    """
    
    def __init__(self, db_session: Optional[Session] = None, policy: Optional[RegulatoryVolumePolicy] = None):
        from sqlalchemy.orm import Session as S
        if db_session is None:
            db_session = db.session
        self.db: S = db_session
        self.policy = policy or RegulatoryVolumePolicy.get_active_or_default()
        self.window_calculator = VolumeWindowCalculator(self.policy)
    
    def _build_base_query(self, account_id: UUID, currency: str):
        """
        Build the base query for eligible DEBIT ledger entries.
        
        Filters applied:
        - Correct account
        - Correct currency
        - DEBIT entries only
        - Transaction is COMPLETED
        - Not a reversal
        """
        # Subquery to identify reversal entries
        reversal_subq = select(LedgerReversalReference.reversal_entry_id).where(
            LedgerReversalReference.reversal_entry_id == LedgerEntryModel.id
        )
        
        query = select(
            func.coalesce(func.sum(LedgerEntryModel.amount), Decimal('0'))
        ).where(
            and_(
                LedgerEntryModel.account_id == account_id,
                LedgerEntryModel.currency == currency,
                LedgerEntryModel.entry_type == EntryType.DEBIT,
                # Transaction must be COMPLETED
                LedgerEntryModel.transaction_id.isnot(None),
                # Not a reversal entry
                not_(exists(reversal_subq)),
            )
        )
        
        return query
    
    def _add_transaction_status_filter(self, query):
        """Join with TransactionModel and filter for COMPLETED status."""
        return query.join(
            TransactionModel,
            LedgerEntryModel.transaction_id == TransactionModel.id
        ).where(
            TransactionModel.status == TransactionStatus.COMPLETED
        )
    
    def get_daily_volume(
        self,
        account_id: UUID,
        currency: str,
        as_of: Optional[datetime] = None
    ) -> Decimal:
        """
        Get total outgoing regulatory volume for an account in a currency
        for the daily window (calendar day or rolling 24h).
        
        Args:
            account_id: Account UUID
            currency: Currency code
            as_of: Optional timestamp to calculate volume as of a specific time
            
        Returns:
            Decimal volume amount
        """
        window_start, window_end = self.window_calculator.get_daily_window_bounds(as_of)
        
        query = self._build_base_query(account_id, currency)
        query = self._add_transaction_status_filter(query)
        query = query.where(
            and_(
                LedgerEntryModel.created_at >= window_start,
                LedgerEntryModel.created_at <= window_end,
            )
        )
        
        result = self.db.execute(query).scalar()
        return result or Decimal('0')
    
    def get_monthly_volume(
        self,
        account_id: UUID,
        currency: str,
        as_of: Optional[datetime] = None
    ) -> Decimal:
        """
        Get total outgoing regulatory volume for an account in a currency
        for the monthly window (calendar month or rolling 30d).
        
        Args:
            account_id: Account UUID
            currency: Currency code
            as_of: Optional timestamp to calculate volume as of a specific time
            
        Returns:
            Decimal volume amount
        """
        window_start, window_end = self.window_calculator.get_monthly_window_bounds(as_of)
        
        query = self._build_base_query(account_id, currency)
        query = self._add_transaction_status_filter(query)
        query = query.where(
            and_(
                LedgerEntryModel.created_at >= window_start,
                LedgerEntryModel.created_at <= window_end,
            )
        )
        
        result = self.db.execute(query).scalar()
        return result or Decimal('0')
    
    def check_daily_limit(
        self,
        account_id: UUID,
        currency: str,
        proposed_amount: Decimal,
        daily_limit: Decimal,
        as_of: Optional[datetime] = None
    ) -> Tuple[bool, Decimal, Decimal]:
        """
        Check if a proposed transaction would exceed the daily regulatory limit.
        
        Args:
            account_id: Account UUID
            currency: Currency code
            proposed_amount: Amount of proposed transaction
            daily_limit: Regulatory daily limit for the account's KYC tier
            as_of: Optional timestamp
            
        Returns:
            (allowed, current_volume, limit)
        """
        if daily_limit is None or daily_limit <= 0:
            return (True, Decimal('0'), daily_limit)
        
        current_volume = self.get_daily_volume(account_id, currency, as_of)
        allowed = (current_volume + proposed_amount) <= daily_limit
        
        return (allowed, current_volume, daily_limit)
    
    def check_monthly_limit(
        self,
        account_id: UUID,
        currency: str,
        proposed_amount: Decimal,
        monthly_limit: Decimal,
        as_of: Optional[datetime] = None
    ) -> Tuple[bool, Decimal, Decimal]:
        """
        Check if a proposed transaction would exceed the monthly regulatory limit.
        
        Args:
            account_id: Account UUID
            currency: Currency code
            proposed_amount: Amount of proposed transaction
            monthly_limit: Regulatory monthly limit for the account's KYC tier
            as_of: Optional timestamp
            
        Returns:
            (allowed, current_volume, limit)
        """
        if monthly_limit is None or monthly_limit <= 0:
            return (True, Decimal('0'), monthly_limit)
        
        current_volume = self.get_monthly_volume(account_id, currency, as_of)
        allowed = (current_volume + proposed_amount) <= monthly_limit
        
        return (allowed, current_volume, monthly_limit)


__all__ = [
    'TimezoneEngine',
    'VolumeWindowCalculator',
    'RegulatoryVolumeCalculator',
]