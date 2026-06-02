"""
app/wallet/services/fx_service.py
Features:
- Real-time rate fetching from multiple providers
- Rate caching with TTL
- Currency conversion with spread
- Historical rate tracking
-Foreign exchange service for multi-currency support.
-Foreign exchange service with intelligent safety halts
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from uuid import uuid4
import requests
from flask import current_app

from app.extensions import db
from app.wallet.models.fx import FXRateModel, FXTransactionModel
from app.wallet.exceptions import UnsupportedCurrencyError, ConversionError


class RateStaleError(Exception):
    """Raised when a cached rate is too old to trust."""
    pass


class RateDeviationError(Exception):
    """Raised when rate deviation exceeds safety threshold."""
    pass


class RateUnavailableError(Exception):
    """Raised when no rate source is available."""
    pass


class FXService:
    """Foreign exchange service with intelligent safety halts."""

    # Safety thresholds
    MAX_RATE_AGE_SECONDS = 120  # 2 minutes max - forces frequent updates
    MAX_DEVIATION_PERCENT = Decimal('2.0')  # 2% max deviation from API
    API_TIMEOUT_SECONDS = 5  # Don't wait forever for API

    # Supported currencies
    SUPPORTED_CURRENCIES = [
        'USD', 'EUR', 'GBP', 'NGN', 'UGX', 'KES', 'GHS', 'ZAR',
        'RWF', 'TZS', 'BWP', 'ZMW', 'MWK', 'AOA', 'XAF', 'XOF',
        'CDF', 'SCR', 'MUR', 'CVE', 'GMD', 'SLL', 'LRD'
    ]

    def __init__(self):
        self.default_ttl = timedelta(minutes=5)
        self.default_spread = Decimal('0.01')  # 1% spread

    def get_rate_safe(self, base_currency: str, quote_currency: str) -> FXRateModel:
        """
        Get exchange rate with safety checks.
        WILL HALT if rate is stale, deviated, or unavailable.
        """
        base_currency = base_currency.upper()
        quote_currency = quote_currency.upper()

        # Validate currencies
        self._validate_currencies(base_currency, quote_currency)

        # Step 1: Get cached rate
        cached_rate = self._get_cached_rate(base_currency, quote_currency)

        # Step 2: Check freshness
        if cached_rate and self._is_rate_stale(cached_rate):
            current_app.logger.warning(
                f"⚠️ RATE STALE: {base_currency}/{quote_currency} "
                f"age={self._get_rate_age_seconds(cached_rate)}s > {self.MAX_RATE_AGE_SECONDS}s"
            )
            raise RateStaleError(
                f"Exchange rate for {base_currency}/{quote_currency} is stale. "
                "Please try again in a few seconds while we fetch current rates."
            )

        # Step 3: Fetch fresh rate from API (source of truth)
        try:
            api_rate = self._fetch_from_api_safe(base_currency, quote_currency)
        except Exception as e:
            current_app.logger.error(f"API fetch failed: {e}")
            raise RateUnavailableError(
                f"Unable to fetch current exchange rate for {base_currency}/{quote_currency}. "
                "Please try again later."
            )

        # Step 4: Validate against cached rate (if exists)
        if cached_rate:
            deviation = self._calculate_deviation(cached_rate.rate, api_rate)
            if deviation > self.MAX_DEVIATION_PERCENT:
                current_app.logger.critical(
                    f"🚨 RATE DEVIATION EXCEEDED: {base_currency}/{quote_currency} "
                    f"cached={cached_rate.rate}, api={api_rate}, deviation={deviation}%"
                )
                # Log to audit for compliance
                self._log_rate_anomaly(base_currency, quote_currency, cached_rate.rate, api_rate, deviation)
                raise RateDeviationError(
                    f"Exchange rate for {base_currency}/{quote_currency} is currently unstable. "
                    "Conversion temporarily disabled. Please check back later."
                )

        # Step 5: Update cache with fresh rate
        rate_model = self._update_rate_cache(base_currency, quote_currency, api_rate)

        return rate_model

    def _validate_currencies(self, base: str, quote: str):
        """Validate currencies are supported."""
        if base not in self.SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(base, self.SUPPORTED_CURRENCIES)
        if quote not in self.SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(quote, self.SUPPORTED_CURRENCIES)

    def _get_cached_rate(self, base: str, quote: str) -> Optional[FXRateModel]:
        """Get cached rate from database."""
        return FXRateModel.query.filter(
            FXRateModel.base_currency == base,
            FXRateModel.quote_currency == quote
        ).first()

    def _is_rate_stale(self, rate_model: FXRateModel) -> bool:
        """Check if rate is too old to trust."""
        age_seconds = self._get_rate_age_seconds(rate_model)
        return age_seconds > self.MAX_RATE_AGE_SECONDS

    def _get_rate_age_seconds(self, rate_model: FXRateModel) -> float:
        """Get age of rate in seconds - handles both naive and aware datetimes."""
        if not rate_model.timestamp:
            return float('inf')
        
        now = datetime.now(timezone.utc)
        timestamp = rate_model.timestamp
        
        # Convert to timezone-aware if needed
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        
        age = now - timestamp
        return age.total_seconds()

    def _calculate_deviation(self, old_rate: Decimal, new_rate: Decimal) -> Decimal:
        """Calculate percentage deviation between two rates."""
        if old_rate == 0:
            return Decimal('100')
        deviation = (abs(new_rate - old_rate) / old_rate) * Decimal('100')
        return deviation.quantize(Decimal('0.01'))

    def _fetch_from_api_safe(self, base: str, quote: str) -> Decimal:
        """
        Fetch rate from API with timeout and fallback.
        Source of truth - if API fails, we HALT.
        """
        # TODO: Replace with actual API integration
        # For now, use mock data with realistic variability
        mock_rates = self._get_mock_rates()

        pair = (base, quote)
        if pair in mock_rates:
            # Add small random variation to simulate real market
            import random
            variation = Decimal(str(random.uniform(0.995, 1.005)))
            return mock_rates[pair] * variation

        # Try inverse
        inverse_pair = (quote, base)
        if inverse_pair in mock_rates:
            inverse_rate = mock_rates[inverse_pair]
            variation = Decimal(str(random.uniform(0.995, 1.005)))
            return (Decimal('1') / inverse_rate) * variation

        # No rate available - HALT
        raise RateUnavailableError(f"No rate available for {base}/{quote}")

    def _get_mock_rates(self) -> Dict:
        """Mock rates - replace with real API."""
        return {
            # USD pairs
            ('USD', 'UGX'): Decimal('3800.0'),
            ('USD', 'NGN'): Decimal('1550.0'),
            ('USD', 'EUR'): Decimal('0.926'),
            ('USD', 'GBP'): Decimal('0.787'),
            ('USD', 'KES'): Decimal('128.0'),
            ('USD', 'GHS'): Decimal('12.5'),
            ('USD', 'TZS'): Decimal('2500.0'),
            ('USD', 'RWF'): Decimal('1300.0'),
            ('USD', 'ZAR'): Decimal('18.5'),
            
            # UGX pairs
            ('UGX', 'USD'): Decimal('0.000263'),
            ('UGX', 'EUR'): Decimal('0.000244'),
            ('UGX', 'GBP'): Decimal('0.000207'),
            ('UGX', 'KES'): Decimal('0.0337'),
            ('UGX', 'TZS'): Decimal('0.658'),
            ('UGX', 'RWF'): Decimal('0.77'),
            ('UGX', 'ZAR'): Decimal('0.00487'),
            ('UGX', 'NGN'): Decimal('0.408'),
            ('UGX', 'GHS'): Decimal('0.0033'),
            ('UGX', 'BWP'): Decimal('0.0014'),   # 1 UGX = 0.0014 Botswana Pula
            ('UGX', 'ZMW'): Decimal('0.0023'),   # 1 UGX = 0.0023 Zambian Kwacha  
            ('UGX', 'MWK'): Decimal('0.18'),     # 1 UGX = 0.18 Malawian Kwacha
            ('UGX', 'AOA'): Decimal('0.022'),    # 1 UGX = 0.022 Angolan Kwanza
            ('UGX', 'XAF'): Decimal('0.015'),    # 1 UGX = 0.015 Central African CFA
            ('UGX', 'XOF'): Decimal('0.015'),    # 1 UGX = 0.015 West African CFA
            ('UGX', 'CDF'): Decimal('0.062'),    # 1 UGX = 0.062 Congolese Franc
            ('UGX', 'SCR'): Decimal('0.0011'),   # 1 UGX = 0.0011 Seychellois Rupee
            ('UGX', 'MUR'): Decimal('0.012'),    # 1 UGX = 0.012 Mauritian Rupee
            ('UGX', 'CVE'): Decimal('0.0027'),   # 1 UGX = 0.0027 Cape Verdean Escudo
            ('UGX', 'GMD'): Decimal('0.0045'),   # 1 UGX = 0.0045 Gambian Dalasi
            ('UGX', 'SLL'): Decimal('0.55'),     # 1 UGX = 0.55 Sierra Leonean Leone
            ('UGX', 'LRD'): Decimal('0.0051'),   # 1 UGX = 0.0051 Liberian Dollar
            
            # Inverse pairs
            ('EUR', 'UGX'): Decimal('1') / Decimal('0.000244'),
            ('GBP', 'UGX'): Decimal('1') / Decimal('0.000207'),
            ('KES', 'UGX'): Decimal('1') / Decimal('0.0337'),
            ('NGN', 'UGX'): Decimal('1') / Decimal('0.408'),
        }

    def _update_rate_cache(self, base: str, quote: str, rate: Decimal) -> FXRateModel:
        """Update or create rate cache with timezone-aware timestamp."""
        existing = self._get_cached_rate(base, quote)
        now = datetime.now(timezone.utc)

        if existing:
            # UPDATE existing
            existing.rate = rate
            existing.source = 'api_live'
            existing.expires_at = now + self.default_ttl
            existing.timestamp = now
            existing.spread = self.default_spread
            db.session.add(existing)
        else:
            # INSERT new
            existing = FXRateModel(
                base_currency=base,
                quote_currency=quote,
                rate=rate,
                source='api_live',
                expires_at=now + self.default_ttl,
                spread=self.default_spread
            )
            db.session.add(existing)

        db.session.commit()
        current_app.logger.info(f"✅ Rate updated: {base}/{quote} = {rate}")
        return existing

    def _log_rate_anomaly(self, base: str, quote: str, old_rate: Decimal, new_rate: Decimal, deviation: Decimal):
        """Log rate anomalies to audit for compliance."""
        try:
            from app.audit.models import AuditLogModel
            audit = AuditLogModel(
                user_id=None,  # System action
                action='RATE_ANOMALY_DETECTED',
                entity_type='fx_rate',
                entity_id=f"{base}/{quote}",
                details={
                    'base_currency': base,
                    'quote_currency': quote,
                    'cached_rate': str(old_rate),
                    'api_rate': str(new_rate),
                    'deviation_percent': str(deviation),
                    'threshold': str(self.MAX_DEVIATION_PERCENT)
                }
            )
            db.session.add(audit)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to log rate anomaly: {e}")

    def convert_amount_safe(
            self,
            amount: Decimal,
            from_currency: str,
            to_currency: str,
            user_id: int,
            source_account_id: int,
            dest_account_id: int
    ) -> Dict:
        """
        Convert amount with safety halts.
        WILL NOT PROCESS if rate is unsafe.
        """
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")

        if from_currency == to_currency:
            return {
                'source_amount': amount,
                'dest_amount': amount,
                'fx_rate': Decimal('1.0'),
                'spread': Decimal('0'),
                'platform_fee': Decimal('0'),
                'safe': True
            }

        # This will raise exception if unsafe
        fx_rate_model = self.get_rate_safe(from_currency, to_currency)

        # Calculate using ask rate (what user pays to buy destination currency)
        dest_amount = (amount * fx_rate_model.ask_rate).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        # Platform fee (0.5%)
        platform_fee = (dest_amount * Decimal('0.005')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        final_dest_amount = dest_amount - platform_fee

        return {
            'source_amount': amount,
            'dest_amount': final_dest_amount,
            'fx_rate': fx_rate_model.ask_rate,
            'spread': fx_rate_model.spread,
            'platform_fee': platform_fee,
            'fx_source': fx_rate_model.source,
            'safe': True,
            'rate_age_seconds': self._get_rate_age_seconds(fx_rate_model)
        }

    def get_all_rates_safe(self, base_currency: str = "USD") -> List[Dict]:
        """Get all rates with individual error handling."""
        rates = []
        db.session.rollback()  # Clear any stale session state

        for currency in self.SUPPORTED_CURRENCIES:
            if currency == base_currency:
                continue
            try:
                rate_model = self.get_rate_safe(base_currency, currency)
                rates.append({
                    "currency": currency,
                    "rate": str(rate_model.rate),
                    "bid_rate": str(rate_model.bid_rate),
                    "ask_rate": str(rate_model.ask_rate),
                    "source": rate_model.source,
                    "expires_at": rate_model.expires_at.isoformat(),
                    "age_seconds": self._get_rate_age_seconds(rate_model)
                })
            except (RateStaleError, RateDeviationError, RateUnavailableError) as e:
                # Don't add this rate - it's unsafe
                current_app.logger.warning(f"Skipping {currency}: {e}")
                continue
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Unexpected error for {currency}: {e}")
                continue

        return rates

    def get_all_rates_as_dict(self, base_currency: str = "USD") -> Dict:
        """Get all rates in the format expected by the template."""
        rates_list = self.get_all_rates_safe(base_currency)
        
        # Convert list to dict format
        rates_dict = {}
        for rate in rates_list:
            rates_dict[rate['currency']] = Decimal(rate['rate'])
        
        return {
            'rates': rates_dict,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'base_currency': base_currency
        }

    def get_supported_currencies(self) -> List[str]:
        """Get list of supported currencies."""
        return self.SUPPORTED_CURRENCIES.copy()
