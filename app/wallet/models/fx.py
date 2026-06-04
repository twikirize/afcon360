"""
app/wallet/models/fx.py
Foreign exchange models for multi-currency support.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Index, UniqueConstraint, BigInteger
from sqlalchemy.ext.declarative import declarative_base

from app.extensions import db


class FXRateModel(db.Model):
    """
    Foreign exchange rate model with caching support.
    
    Stores currency pair rates with timestamps for rate staleness detection.
    """
    __tablename__ = 'fx_rates'

    id = Column(BigInteger, primary_key=True)
    base_currency = Column(String(3), nullable=False, index=True)  # e.g., USD
    quote_currency = Column(String(3), nullable=False, index=True)  # e.g., UGX
    rate = Column(Numeric(20, 8), nullable=False)  # Exchange rate (1 base = rate quote)
    source = Column(String(50), nullable=False)  # Rate source (xe.com, central_bank, etc.)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    spread = Column(Numeric(10, 6), default=Decimal('0.01'))  # Platform spread in percentage
    
    # Composite unique constraint for active rates
    __table_args__ = (
        UniqueConstraint('base_currency', 'quote_currency', name='uq_fx_pair'),
        Index('idx_fx_pair_timestamp', 'base_currency', 'quote_currency', 'timestamp'),
    )

    @property
    def is_expired(self):
        """Check if rate is expired."""
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def bid_rate(self):
        """Rate for selling base currency (includes spread)."""
        return self.rate * (Decimal('1') - self.spread / Decimal('100'))

    @property
    def ask_rate(self):
        """Rate for buying base currency (includes spread)."""
        return self.rate * (Decimal('1') + self.spread / Decimal('100'))

    def to_dict(self):
        return {
            'base_currency': self.base_currency,
            'quote_currency': self.quote_currency,
            'rate': str(self.rate),
            'bid_rate': str(self.bid_rate),
            'ask_rate': str(self.ask_rate),
            'spread': str(self.spread),
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'expires_at': self.expires_at.isoformat(),
        }


class FXTransactionModel(db.Model):
    """
    Foreign exchange transaction model for tracking currency conversions.
    
    Records all currency conversions with source/destination details.
    """
    __tablename__ = 'fx_transactions'

    id = Column(BigInteger, primary_key=True)
    transaction_id = Column(String(64), nullable=False, unique=True, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    
    # Source currency details
    source_currency = Column(String(3), nullable=False)
    source_amount = Column(Numeric(20, 2), nullable=False)
    source_account_id = Column(BigInteger, nullable=False)
    
    # Destination currency details
    dest_currency = Column(String(3), nullable=False)
    dest_amount = Column(Numeric(20, 2), nullable=False)
    dest_account_id = Column(BigInteger, nullable=False)
    
    # FX details
    fx_rate = Column(Numeric(20, 8), nullable=False)
    fx_source = Column(String(50), nullable=False)
    spread = Column(Numeric(10, 6), nullable=False)
    platform_fee = Column(Numeric(20, 2), default=Decimal('0'))
    
    # Status
    status = Column(String(20), nullable=False, default='pending', index=True)  # pending, completed, failed
    error_message = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_fx_user_status', 'user_id', 'status'),
        Index('idx_fx_created_at', 'created_at'),
    )

    def to_dict(self):
        return {
            'transaction_id': self.transaction_id,
            'user_id': self.user_id,
            'source_currency': self.source_currency,
            'source_amount': str(self.source_amount),
            'dest_currency': self.dest_currency,
            'dest_amount': str(self.dest_amount),
            'fx_rate': str(self.fx_rate),
            'fx_source': self.fx_source,
            'spread': str(self.spread),
            'platform_fee': str(self.platform_fee),
            'status': self.status,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
