"""
Rate Limiting Configuration Service
Provides owner-configurable rate limit settings with caching and runtime wiring.
"""

import json
import logging
from typing import Any, Dict, Optional, List

from app.extensions import db, cache
from app.admin.owner.models import RateLimitSettings

logger = logging.getLogger(__name__)


class RateLimitService:
    """Service for managing rate limiting configuration"""

    CACHE_PREFIX = "rate_limit:settings"
    CACHE_TTL = 60  # 1 minute

    # Known endpoint limit keys
    ENDPOINT_KEYS = [
        'register', 'login', 'password_reset', 'media_upload',
        'media_admin', 'accommodation_checkout', 'accommodation_cancel',
        'accommodation_host_actions', 'wallet_pin', 'wallet_deposit',
        'wallet_withdraw', 'wallet_transfer', 'event_create', 'event_checkin',
        'transport_provider_registration', 'transport_vehicle_registration',
        'transport_driver_status_update',
    ]

    @staticmethod
    def _build_cache_key(key: str) -> str:
        return f"{RateLimitService.CACHE_PREFIX}:{key}"

    @staticmethod
    def get_setting(key: str, default: Any = None) -> Any:
        """Get a single rate limit setting with cache"""
        cache_key = RateLimitService._build_cache_key(key)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        settings = RateLimitSettings.get_settings()
        value = getattr(settings, key, default)
        cache.set(cache_key, value, timeout=RateLimitService.CACHE_TTL)
        return value

    @staticmethod
    def get_all_settings() -> Dict[str, Any]:
        """Get all rate limit settings as a dictionary"""
        settings = RateLimitSettings.get_settings()
        return {
            'enabled': settings.enabled,
            'strategy': settings.strategy,
            'default_per_minute': settings.default_per_minute,
            'default_per_hour': settings.default_per_hour,
            'default_per_day': settings.default_per_day,
            'block_duration_minutes': settings.block_duration_minutes,
            'progressive_blocking_enabled': settings.progressive_blocking_enabled,
            'max_violations_before_block': settings.max_violations_before_block,
            'key_sources': settings.key_sources,
            'logging_enabled': settings.logging_enabled,
            'alert_on_breach': settings.alert_on_breach,
            'alert_threshold_per_minute': settings.alert_threshold_per_minute,
            'edge_rate_limiting_enabled': settings.edge_rate_limiting_enabled,
        }

    @staticmethod
    def update_settings(updates: Dict[str, Any], updated_by: int = None) -> bool:
        """Update rate limit settings and clear cache"""
        try:
            settings = RateLimitSettings.get_settings()
            for key, value in updates.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)
            settings.updated_by = updated_by
            db.session.commit()

            # Clear cache
            for key in updates.keys():
                cache_key = RateLimitService._build_cache_key(key)
                cache.delete(cache_key)

            # Clear any cached full settings
            cache.delete(RateLimitService.CACHE_PREFIX)

            logger.info(f"Rate limit settings updated by user {updated_by}: {updates}")
            return True
        except Exception as e:
            logger.error(f"Failed to update rate limit settings: {e}")
            db.session.rollback()
            return False

    @staticmethod
    def is_enabled() -> bool:
        """Check if rate limiting is globally enabled"""
        return RateLimitService.get_setting('enabled', True)

    @staticmethod
    def get_strategy() -> str:
        """Get current rate limiting strategy"""
        return RateLimitService.get_setting('strategy', 'fixed-window')

    @staticmethod
    def get_default_limits() -> List[str]:
        """Get default rate limits in Flask-Limiter format"""
        per_minute = RateLimitService.get_setting('default_per_minute', 500)
        per_hour = RateLimitService.get_setting('default_per_hour', 2000)
        per_day = RateLimitService.get_setting('default_per_day', 10000)
        return [
            f"{per_minute} per minute",
            f"{per_hour} per hour",
            f"{per_day} per day",
        ]

    @staticmethod
    def get_key_sources() -> List[str]:
        """Get configured key sources (identities)"""
        sources = RateLimitService.get_setting('key_sources', 'ip,user_id')
        return [s.strip() for s in sources.split(',') if s.strip()]

    @staticmethod
    def get_block_duration_minutes() -> int:
        """Get block duration in minutes"""
        return RateLimitService.get_setting('block_duration_minutes', 15)

    @staticmethod
    def is_progressive_blocking_enabled() -> bool:
        """Check if progressive blocking is enabled"""
        return RateLimitService.get_setting('progressive_blocking_enabled', False)

    @staticmethod
    def get_max_violations_before_block() -> int:
        """Get max violations before temporary block"""
        return RateLimitService.get_setting('max_violations_before_block', 10)

    @staticmethod
    def is_logging_enabled() -> bool:
        """Check if rate limit breach logging is enabled"""
        return RateLimitService.get_setting('logging_enabled', True)

    @staticmethod
    def is_alert_on_breach() -> bool:
        """Check if breach alerting is enabled"""
        return RateLimitService.get_setting('alert_on_breach', False)

    @staticmethod
    def is_edge_rate_limiting_enabled() -> bool:
        """Check if edge-layer rate limiting is enabled"""
        return RateLimitService.get_setting('edge_rate_limiting_enabled', False)

    @staticmethod
    def get_security_status() -> Dict[str, Any]:
        """Get rate limiting status for security dashboard"""
        return {
            'enabled': RateLimitService.is_enabled(),
            'strategy': RateLimitService.get_strategy(),
            'default_limits': RateLimitService.get_default_limits(),
            'block_duration_minutes': RateLimitService.get_block_duration_minutes(),
            'progressive_blocking': RateLimitService.is_progressive_blocking_enabled(),
            'key_sources': RateLimitService.get_key_sources(),
            'edge_rate_limiting': RateLimitService.is_edge_rate_limiting_enabled(),
            'logging_enabled': RateLimitService.is_logging_enabled(),
            'alert_on_breach': RateLimitService.is_alert_on_breach(),
            'timestamp': None,  # Will be set by caller
        }
