"""
Security Settings Service for AFCON360
Provides centralized access to system settings with caching and fallbacks
"""
import json
import logging
from functools import lru_cache
from typing import Any, Optional, Dict
from datetime import datetime, timedelta

from app.extensions import db, cache
from app.admin.owner.models import SystemSetting
from app.config import Config

logger = logging.getLogger(__name__)


class SecuritySettingsService:
    """Service for managing security settings with caching"""

    CACHE_PREFIX = "system:settings"
    CACHE_TTL = 300  # 5 minutes

    @staticmethod
    @lru_cache(maxsize=128)
    def get_setting(key: str, default: Any = None) -> Any:
        """
        Get a system setting with caching.
        Priority: Database -> Config -> Environment -> Default
        """
        # Try cache first
        cache_key = f"{SecuritySettingsService.CACHE_PREFIX}:{key}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # Try database
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            # Convert value based on type
            if setting.value_type == 'bool':
                value = setting.value.lower() in ('true', '1', 'yes', 'on') if setting.value else False
            elif setting.value_type == 'int':
                try:
                    value = int(setting.value)
                except:
                    value = None
            elif setting.value_type == 'json':
                try:
                    value = json.loads(setting.value) if setting.value else {}
                except:
                    value = {}
            else:
                value = setting.value
            # Cache the value
            cache.set(cache_key, value, timeout=SecuritySettingsService.CACHE_TTL)
            return value

        # Try config
        config_value = getattr(Config, key.upper(), None)
        if config_value is not None:
            cache.set(cache_key, config_value, timeout=SecuritySettingsService.CACHE_TTL)
            return config_value

        # Try MODULE_FLAGS
        if key.lower() in Config.MODULE_FLAGS:
            value = Config.MODULE_FLAGS[key.lower()]
            cache.set(cache_key, value, timeout=SecuritySettingsService.CACHE_TTL)
            return value

        # Try WALLET_FEATURES
        if key.lower().startswith('wallet_'):
            wallet_key = key.lower().replace('wallet_', '')
            if wallet_key in Config.WALLET_FEATURES:
                value = Config.WALLET_FEATURES[wallet_key]
                cache.set(cache_key, value, timeout=SecuritySettingsService.CACHE_TTL)
                return value

        # Return default
        cache.set(cache_key, default, timeout=SecuritySettingsService.CACHE_TTL)
        return default

    @staticmethod
    def set_setting(key: str, value: Any, value_type: str = 'str',
                   category: str = 'general', description: str = None,
                   is_public: bool = False, requires_restart: bool = False,
                   updated_by: int = None) -> bool:
        """Set a system setting and clear cache"""
        try:
            # Get old value for audit
            old_setting = SystemSetting.query.filter_by(key=key).first()
            old_value = old_setting.value if old_setting else None

            setting = SystemSetting.set(
                key=key,
                value=value,
                value_type=value_type,
                category=category,
                description=description,
                is_public=is_public,
                requires_restart=requires_restart,
                updated_by=updated_by
            )

            db.session.commit()

            # Audit system setting change
            from app.audit.comprehensive_audit import AuditService
            from flask import request

            try:
                AuditService.data_change(
                    entity_type="system_setting",
                    entity_id=key,
                    operation="update",
                    old_value={"value": old_value, "value_type": old_setting.value_type if old_setting else None},
                    new_value={"value": value, "value_type": value_type},
                    changed_by=updated_by,
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request and request.user_agent else None,
                    extra_data={
                        "category": category,
                        "description": description,
                        "is_public": is_public,
                        "requires_restart": requires_restart
                    }
                )
            except Exception as audit_error:
                logger.error(f"Failed to audit system setting change: {audit_error}")

            # Clear cache
            cache_key = f"{SecuritySettingsService.CACHE_PREFIX}:{key}"
            cache.delete(cache_key)

            # Clear lru_cache
            SecuritySettingsService.get_setting.cache_clear()

            logger.info(f"System setting updated: {key} = {value}")
            return True

        except Exception as e:
            logger.error(f"Error setting system setting {key}: {e}")
            db.session.rollback()
            return False

    @staticmethod
    def is_feature_enabled(feature_key: str, default: bool = False) -> bool:
        """Check if a feature is enabled"""
        value = SecuritySettingsService.get_setting(feature_key, default)
        return bool(value)

    @staticmethod
    def get_feature_flags() -> Dict[str, bool]:
        """Get all feature flags"""
        flags = {}

        # Database flags
        db_flags = SystemSetting.query.filter_by(category='feature').all()
        for flag in db_flags:
            flags[flag.key] = bool(flag.get(flag.key))

        # Config flags
        for key, value in Config.MODULE_FLAGS.items():
            flags[f"ENABLE_{key.upper()}"] = value

        return flags

    @staticmethod
    def get_security_status() -> Dict[str, Any]:
        """Get comprehensive security status"""
        return {
            'lockdown': SecuritySettingsService.is_feature_enabled('EMERGENCY_LOCKDOWN', False),
            'maintenance': SecuritySettingsService.is_feature_enabled('MAINTENANCE_MODE', False),
            'rate_limiting': SecuritySettingsService.is_feature_enabled('RATE_LIMIT_ENABLED', True),
            'security_headers': SecuritySettingsService.is_feature_enabled('SECURITY_HEADERS_ENABLED', True),
            'audit_logging': SecuritySettingsService.is_feature_enabled('AUDIT_LOGGING_ENABLED', True),
            'wallet_enabled': SecuritySettingsService.is_feature_enabled('ENABLE_WALLET', True),
            'payment_processing': SecuritySettingsService.is_feature_enabled('PAYMENT_PROCESSING_ENABLED', False),
            'timestamp': datetime.utcnow().isoformat()
        }

    @staticmethod
    def activate_lockdown(activated_by: int) -> bool:
        """Activate emergency lockdown"""
        try:
            # Set lockdown flag
            SecuritySettingsService.set_setting(
                key='EMERGENCY_LOCKDOWN',
                value=True,
                value_type='bool',
                category='security',
                description='Emergency lockdown activated',
                updated_by=activated_by
            )

            # Disable non-essential features
            non_essential = ['ENABLE_WALLET', 'PAYMENT_PROCESSING_ENABLED']
            for feature in non_essential:
                SecuritySettingsService.set_setting(
                    key=feature,
                    value=False,
                    value_type='bool',
                    category='feature',
                    description=f'Disabled during lockdown',
                    updated_by=activated_by
                )

            logger.critical(f"EMERGENCY LOCKDOWN ACTIVATED by user {activated_by}")
            return True

        except Exception as e:
            logger.error(f"Failed to activate lockdown: {e}")
            return False

    @staticmethod
    def toggle_feature_flag(feature_key: str, enabled: bool, toggled_by: int, reason: str = None) -> bool:
        """Toggle a feature flag with audit logging"""
        try:
            # Get old value for audit
            old_value = SecuritySettingsService.is_feature_enabled(feature_key, False)

            # Set the new value
            success = SecuritySettingsService.set_setting(
                key=feature_key,
                value=enabled,
                value_type='bool',
                category='feature',
                description=f'Feature flag toggled: {reason}' if reason else f'Feature flag toggled',
                updated_by=toggled_by
            )

            if success:
                # Additional audit logging for feature flag changes
                from app.audit.comprehensive_audit import AuditService
                from flask import request

                try:
                    AuditService.data_change(
                        entity_type="feature_flag",
                        entity_id=feature_key,
                        operation="toggle",
                        old_value={"enabled": old_value},
                        new_value={"enabled": enabled},
                        changed_by=toggled_by,
                        ip_address=request.remote_addr if request else None,
                        user_agent=request.user_agent.string if request and request.user_agent else None,
                        extra_data={
                            "reason": reason,
                            "toggled_by": toggled_by,
                            "feature_key": feature_key
                        }
                    )
                except Exception as audit_error:
                    logger.error(f"Failed to audit feature flag toggle: {audit_error}")

                logger.info(f"Feature flag {feature_key} toggled to {enabled} by user {toggled_by}")

            return success

        except Exception as e:
            logger.error(f"Failed to toggle feature flag {feature_key}: {e}")
            return False

    @staticmethod
    def deactivate_lockdown(deactivated_by: int) -> bool:
        """Deactivate emergency lockdown"""
        try:
            SecuritySettingsService.set_setting(
                key='EMERGENCY_LOCKDOWN',
                value=False,
                value_type='bool',
                category='security',
                description='Emergency lockdown deactivated',
                updated_by=deactivated_by
            )

            logger.info(f"Emergency lockdown deactivated by user {deactivated_by}")
            return True

        except Exception as e:
            logger.error(f"Failed to deactivate lockdown: {e}")
            return False


# Global instance
security_settings = SecuritySettingsService()
