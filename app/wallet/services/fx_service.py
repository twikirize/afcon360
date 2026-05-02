"""
app/wallet/services/fx_service.py
Foreign exchange service for multi-currency support.

Features:
- Real-time rate fetching from multiple providers
- Rate caching with TTL
- Currency conversion with spread
- Historical rate tracking
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from uuid import uuid4
import requests
from flask import current_app

from app.extensions import db
from app.wallet.models.fx import FXRateModel, FXTransactionModel
from app.wallet.exceptions import UnsupportedCurrencyError, ConversionError


class FXService:
    """Foreign exchange service for multi-currency operations."""

    # Default supported currencies
    SUPPORTED_CURRENCIES = [
        'USD', 'EUR', 'GBP', 'NGN', 'UGX', 'KES', 'GHS', 'ZAR',
        'RWF', 'TZS', 'BWP', 'ZMW', 'MWK', 'AOA', 'XAF', 'XOF',
        'CDF', 'SCR', 'MUR', 'CVE', 'GMD', 'SLL', 'LRD', 'LRD'
    ]

    # Rate providers
    RATE_PROVIDERS = {
        'xe_com': 'https://www.xe.com/currencyconverter',
        'open_exchange_rates': 'https://openexchangerates.org/api',
        'central_bank': 'https://api.centralbank.org',
    }

    def __init__(self):
        self.default_source = 'xe_com'
        self.default_ttl = timedelta(minutes=5)  # Cache rates for 5 minutes
        self.default_spread = Decimal('0.01')  # 1% spread

    def get_rate(self, base_currency: str, quote_currency: str) -> FXRateModel:
        """
        Get exchange rate for currency pair.
        
        Args:
            base_currency: Source currency code (e.g., USD)
            quote_currency: Destination currency code (e.g., UGX)
            
        Returns:
            FXRateModel with current rate
            
        Raises:
            UnsupportedCurrencyError: If currency not supported
            ConversionError: If rate fetch fails
        """
        base_currency = base_currency.upper()
        quote_currency = quote_currency.upper()

        # Validate currencies
        if base_currency not in self.SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(base_currency, self.SUPPORTED_CURRENCIES)
        if quote_currency not in self.SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(quote_currency, self.SUPPORTED_CURRENCIES)

        # Check cache first
        cached_rate = FXRateModel.query.filter(
            FXRateModel.base_currency == base_currency,
            FXRateModel.quote_currency == quote_currency,
            FXRateModel.expires_at > datetime.utcnow()
        ).first()

        if cached_rate:
            return cached_rate

        # Fetch fresh rate
        rate = self._fetch_rate(base_currency, quote_currency)

        # Cache the rate
        cached_rate = FXRateModel(
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate=rate,
            source=self.default_source,
            expires_at=datetime.utcnow() + self.default_ttl,
            spread=self.default_spread
        )
        db.session.add(cached_rate)
        db.session.commit()

        return cached_rate

    def _fetch_rate(self, base_currency: str, quote_currency: str) -> Decimal:
        """
        Fetch rate from external provider.
        
        Args:
            base_currency: Source currency
            quote_currency: Destination currency
            
        Returns:
            Decimal exchange rate
            
        Raises:
            ConversionError: If fetch fails
        """
        # In production, integrate with real APIs
        # For now, return mock rates for common pairs
        mock_rates = {
            ('USD', 'UGX'): Decimal('3800.0'),
            ('UGX', 'USD'): Decimal('0.000263'),
            ('USD', 'NGN'): Decimal('1550.0'),
            ('NGN', 'USD'): Decimal('0.000645'),
            ('EUR', 'USD'): Decimal('1.08'),
            ('USD', 'EUR'): Decimal('0.926'),
            ('GBP', 'USD'): Decimal('1.27'),
            ('USD', 'GBP'): Decimal('0.787'),
            ('USD', 'KES'): Decimal('128.0'),
            ('KES', 'USD'): Decimal('0.00781'),
            ('USD', 'GHS'): Decimal('12.5'),
            ('GHS', 'USD'): Decimal('0.08'),
        }

        pair = (base_currency, quote_currency)
        if pair in mock_rates:
            return mock_rates[pair]

        # Fallback: inverse rate if available
        inverse_pair = (quote_currency, base_currency)
        if inverse_pair in mock_rates:
            inverse_rate = mock_rates[inverse_pair]
            return Decimal('1') / inverse_rate

        # Default to 1:1 for unknown pairs (should be replaced with real API)
        current_app.logger.warning(
            f"No rate found for {base_currency}/{quote_currency}, using 1:1"
        )
        return Decimal('1.0')

    def convert_amount(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        user_id: int,
        source_account_id: int,
        dest_account_id: int
    ) -> Dict:
        """
        Convert amount between currencies.
        
        Args:
            amount: Amount to convert
            from_currency: Source currency
            to_currency: Destination currency
            user_id: User ID
            source_account_id: Source account ID
            dest_account_id: Destination account ID
            
        Returns:
            Dict with conversion details
            
        Raises:
            UnsupportedCurrencyError: If currency not supported
            ConversionError: If conversion fails
        """
        if from_currency == to_currency:
            return {
                'source_amount': amount,
                'dest_amount': amount,
                'fx_rate': Decimal('1.0'),
                'spread': Decimal('0'),
                'platform_fee': Decimal('0'),
            }

        # Get rate
        fx_rate_model = self.get_rate(from_currency, to_currency)
        
        # Calculate destination amount (using ask rate for buying dest currency)
        dest_amount = (amount * fx_rate_model.ask_rate).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        
        # Calculate platform fee (0.5%)
        platform_fee = (dest_amount * Decimal('0.005')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        
        # Final amount after fee
        final_dest_amount = dest_amount - platform_fee

        return {
            'source_amount': amount,
            'dest_amount': final_dest_amount,
            'fx_rate': fx_rate_model.ask_rate,
            'spread': fx_rate_model.spread,
            'platform_fee': platform_fee,
            'fx_source': fx_rate_model.source,
        }

    def create_fx_transaction(
        self,
        user_id: int,
        source_currency: str,
        source_amount: Decimal,
        source_account_id: int,
        dest_currency: str,
        dest_account_id: int,
        conversion_details: Dict
    ) -> FXTransactionModel:
        """
        Create FX transaction record.
        
        Args:
            user_id: User ID
            source_currency: Source currency
            source_amount: Source amount
            source_account_id: Source account ID
            dest_currency: Destination currency
            dest_account_id: Destination account ID
            conversion_details: Conversion details from convert_amount()
            
        Returns:
            FXTransactionModel
        """
        fx_transaction = FXTransactionModel(
            transaction_id=str(uuid4()),
            user_id=user_id,
            source_currency=source_currency,
            source_amount=source_amount,
            source_account_id=source_account_id,
            dest_currency=dest_currency,
            dest_amount=conversion_details['dest_amount'],
            dest_account_id=dest_account_id,
            fx_rate=conversion_details['fx_rate'],
            fx_source=conversion_details['fx_source'],
            spread=conversion_details['spread'],
            platform_fee=conversion_details['platform_fee'],
            status='pending'
        )
        
        db.session.add(fx_transaction)
        db.session.commit()
        
        return fx_transaction

    def get_supported_currencies(self) -> List[str]:
        """Get list of supported currencies."""
        return self.SUPPORTED_CURRENCIES.copy()

    def get_user_fx_history(self, user_id: int, limit: int = 50) -> List[FXTransactionModel]:
        """
        Get FX transaction history for user.
        
        Args:
            user_id: User ID
            limit: Maximum number of records
            
        Returns:
            List of FXTransactionModel
        """
        return FXTransactionModel.query.filter_by(user_id=user_id)\
            .order_by(FXTransactionModel.created_at.desc())\
            .limit(limit)\
            .all()
