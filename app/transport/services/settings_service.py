#app/transport/services/settings_service.py
"""
AFCON360 Transport Module - Production Settings Service
Enterprise-grade settings management with audit, validation, and security
"""
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from functools import wraps, lru_cache
from enum import Enum
from dataclasses import dataclass
from decimal import Decimal

from flask import current_app, request, g
from sqlalchemy import or_, and_, func, text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.extensions import db, cache, redis_client, limiter
from app.transport.models import TransportSetting, get_setting, update_setting

from app.utils.exceptions import (
    ValidationError, PermissionError, RateLimitError,
    ServiceUnavailableError, ConflictError, NotFoundError
)
from app.utils.security import (  # FIXED: settings → security
    verify_permission,require_permission, sanitize_input, encrypt_field,
    decrypt_field, generate_secure_token, validate_csrf
)
from app.utils.monitoring import (
    monitor_endpoint, record_metric, start_span,
    track_operation, with_circuit_breaker
)
from app.utils.caching import (
    cached_query, invalidate_cache_pattern,
    with_cache_lock, cache_invalidate_on_change,
    get_cached, set_cached, delete_cached
)
from app.utils.audit import audit_log
from app.utils.rate_limiting import rate_limit
from app.utils.idempotency import idempotent_request

logger = logging.getLogger(__name__)


class SettingDataType(Enum):
    """Setting data types"""
    BOOLEAN = 'boolean'
    INTEGER = 'integer'
    DECIMAL = 'decimal'
    STRING = 'string'
    JSON = 'json'
    ARRAY = 'array'
    OBJECT = 'object'


class SettingCategory(Enum):
    """Setting categories"""
    GENERAL = 'general'
    PROVIDER = 'provider'
    BOOKING = 'booking'
    PAYMENT = 'payment'
    SAFETY = 'safety'
    INTEGRATIONS = 'integrations'
    INTELLIGENCE = 'intelligence'
    NOTIFICATIONS = 'notifications'
    PERFORMANCE = 'performance'
    MONITORING = 'monitoring'
    SECURITY = 'security'
    ADVANCED = 'advanced'


@dataclass
class SettingValidationResult:
    """Setting validation result"""
    valid: bool
    errors: List[str]
    normalized_value: Any
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class SettingUpdateResult:
    """Setting update result"""
    success: bool
    updated_count: int
    failed_keys: List[str]
    requires_restart: bool
    warnings: List[str]
    errors: List[Dict[str, Any]]

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.errors is None:
            self.errors = []


class SettingsService:
    """Production-grade settings management service"""

    # Cache configuration
    CACHE_PREFIX = "transport:settings"
    CACHE_TTL = 300  # 5 minutes
    CACHE_VERSION = "v1"

    # Rate limiting
    RATE_LIMITS = {
        'update_settings': '10 per minute',
        'reset_settings': '3 per hour',
        'export_settings': '20 per hour'
    }

    @staticmethod
    @monitor_endpoint("get_all_settings")
    @require_permission("settings:read")
    @cached_query(lambda category=None, include_advanced=False, **kwargs:
                 f"{SettingsService.CACHE_PREFIX}:all:{category or 'all'}:{include_advanced}")
    def get_all_settings(category: Optional[str] = None,
                         include_advanced: bool = False,
                         include_sensitive: bool = False) -> List[Dict[str, Any]]:
        """
        Get all settings with proper security filtering

        Args:
            category: Filter by category
            include_advanced: Include advanced settings
            include_sensitive: Include sensitive settings (requires permission)

        Returns:
            List of setting dictionaries
        """
        try:
            query = TransportSetting.query.filter_by(is_deleted=False)

            # Apply category filter
            if category:
                query = query.filter_by(category=category)

            # Apply advanced filter
            if not include_advanced:
                query = query.filter_by(is_advanced=False)

            # Apply sensitive filter
            if not include_sensitive and not g.user.has_permission('settings:view_sensitive'):
                query = query.filter_by(is_public=True)

            # Order by category and key
            settings = query.order_by(
                TransportSetting.category,
                TransportSetting.key
            ).all()

            # Convert to safe dict format
            result = []
            for setting in settings:
                setting_dict = setting.to_safe_dict()

                # Include value for authorized users
                if (setting.is_public or
                    include_sensitive or
                    g.user.has_permission('settings:view_sensitive')):
                    setting_dict['value'] = setting.value

                result.append(setting_dict)

            # Record metrics
            record_metric(
                'settings_queried',
                tags={
                    'category': category or 'all',
                    'count': len(result)
                },
                value=len(result)
            )

            return result

        except SQLAlchemyError as e:
            logger.error(f"Database error getting settings: {e}", exc_info=True)
            record_metric('settings_queried', tags={'status': 'failed'}, value=1)
            raise ServiceUnavailableError(
                message="Settings service unavailable",
                code="SETTINGS_SERVICE_UNAVAILABLE"
            )

    @staticmethod
    @monitor_endpoint("get_categories")
    @cached_query(lambda **kwargs: f"{SettingsService.CACHE_PREFIX}:categories")
    def get_categories() -> List[str]:
        """Get distinct setting categories"""
        try:
            categories = db.session.query(
                TransportSetting.category
            ).filter_by(
                is_deleted=False,
                is_public=True
            ).distinct().order_by(
                TransportSetting.category
            ).all()

            return [category[0] for category in categories]

        except SQLAlchemyError as e:
            logger.error(f"Database error getting categories: {e}")
            return []

    @staticmethod
    @monitor_endpoint("update_settings")
    @rate_limit("update_settings", limit=10, period=60)
    @require_permission("settings:write")
    @idempotent_request('settings_update', ttl=30)
    def update_settings(settings_dict: Dict[str, Any],
                       user_id: Optional[int] = None,
                       request_id: Optional[str] = None) -> SettingUpdateResult:
        """
        Update multiple settings with validation and audit

        Args:
            settings_dict: Dictionary of settings to update
            user_id: User making the updates
            request_id: Unique request ID

        Returns:
            SettingUpdateResult with update status
        """
        span = start_span("update_settings")
        span.set_attribute("settings.count", len(settings_dict))

        try:
            # Validate CSRF token
            if request and not validate_csrf(request):
                raise PermissionError(
                    message="Invalid CSRF token",
                    code="INVALID_CSRF_TOKEN"
                )

            # Sanitize input
            sanitized_settings = sanitize_input(settings_dict)

            # Track results
            updated_keys = []
            failed_keys = []
            errors = []
            warnings = []
            requires_restart = False

            # Process each setting
            for key, value in sanitized_settings.items():
                try:
                    # Get setting with validation
                    setting = TransportSetting.query.filter_by(
                        key=key,
                        is_deleted=False
                    ).first()

                    if not setting:
                        errors.append({
                            'key': key,
                            'error': 'Setting not found',
                            'code': 'SETTING_NOT_FOUND'
                        })
                        failed_keys.append(key)
                        continue

                    # Check permissions for sensitive settings
                    if not setting.is_public and not g.user.has_permission('settings:edit_sensitive'):
                        errors.append({
                            'key': key,
                            'error': 'Insufficient permissions',
                            'code': 'PERMISSION_DENIED'
                        })
                        failed_keys.append(key)
                        continue

                    # Validate value
                    validation_result = SettingsService._validate_setting_value(
                        setting=setting,
                        value=value
                    )

                    if not validation_result.valid:
                        errors.append({
                            'key': key,
                            'error': 'Validation failed',
                            'details': validation_result.errors,
                            'code': 'VALIDATION_FAILED'
                        })
                        failed_keys.append(key)
                        continue

                    # Track restart requirement
                    if setting.requires_restart:
                        requires_restart = True

                    # Add warnings
                    if validation_result.warnings:
                        warnings.extend([
                            f"{key}: {warning}"
                            for warning in validation_result.warnings
                        ])

                    # Update setting
                    success = update_setting(
                        key=key,
                        value=validation_result.normalized_value,
                        modified_by=user_id
                    )

                    if success:
                        updated_keys.append(key)
                    else:
                        errors.append({
                            'key': key,
                            'error': 'Update failed',
                            'code': 'UPDATE_FAILED'
                        })
                        failed_keys.append(key)

                except Exception as e:
                    logger.error(f"Error updating setting {key}: {e}", exc_info=True)
                    errors.append({
                        'key': key,
                        'error': str(e),
                        'code': 'INTERNAL_ERROR'
                    })
                    failed_keys.append(key)

            # Create audit log
            if updated_keys:
                audit_log(
                    action='settings_updated',
                    entity_type='settings',
                    user_id=user_id,
                    details={
                        'updated_keys': updated_keys,
                        'failed_keys': failed_keys,
                        'requires_restart': requires_restart,
                        'request_id': request_id
                    },
                    request_id=request_id
                )

            # Invalidate cache
            invalidate_cache_pattern(f"{SettingsService.CACHE_PREFIX}:*")

            # Record metrics
            record_metric(
                'settings_updated',
                tags={
                    'success_count': len(updated_keys),
                    'failed_count': len(failed_keys)
                },
                value=len(updated_keys)
            )

            span.set_status("OK")
            return SettingUpdateResult(
                success=len(failed_keys) == 0,
                updated_count=len(updated_keys),
                failed_keys=failed_keys,
                requires_restart=requires_restart,
                warnings=warnings,
                errors=errors
            )

        except (PermissionError, ValidationError) as e:
            span.set_status("ERROR", str(e))
            record_metric('settings_updated', tags={'status': 'failed'}, value=1)
            raise

        except SQLAlchemyError as e:
            logger.error(f"Database error updating settings: {e}", exc_info=True)
            span.set_status("ERROR", f"Database error: {str(e)}")
            record_metric('settings_updated', tags={'status': 'failed'}, value=1)
            raise ServiceUnavailableError(
                message="Settings service unavailable",
                code="SETTINGS_SERVICE_UNAVAILABLE"
            )

        except Exception as e:
            logger.error(f"Unexpected error updating settings: {e}", exc_info=True)
            span.set_status("ERROR", f"Unexpected error: {str(e)}")
            record_metric('settings_updated', tags={'status': 'failed'}, value=1)
            raise

        finally:
            span.end()

    @staticmethod
    @monitor_endpoint("reset_to_defaults")
    @rate_limit("reset_settings", limit=3, period=3600)
    @require_permission("settings:reset")
    def reset_to_defaults(user_id: Optional[int] = None,
                         request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Reset all settings to factory defaults

        Args:
            user_id: User performing reset
            request_id: Unique request ID

        Returns:
            Dict with reset result
        """
        span = start_span("reset_settings")

        try:
            # Get all settings
            settings = TransportSetting.query.filter_by(is_deleted=False).all()

            reset_count = 0
            failed_keys = []

            for setting in settings:
                try:
                    # Reset to default value
                    if setting.default_value is not None:
                        success = update_setting(
                            key=setting.key,
                            value=setting.default_value,
                            modified_by=user_id
                        )

                        if success:
                            reset_count += 1
                        else:
                            failed_keys.append(setting.key)
                except Exception as e:
                    logger.error(f"Error resetting setting {setting.key}: {e}")
                    failed_keys.append(setting.key)

            # Create audit log
            audit_log(
                action='settings_reset',
                entity_type='settings',
                user_id=user_id,
                details={
                    'reset_count': reset_count,
                    'failed_keys': failed_keys
                },
                request_id=request_id
            )

            # Invalidate cache
            invalidate_cache_pattern(f"{SettingsService.CACHE_PREFIX}:*")

            # Record metrics
            record_metric('settings_reset', value=reset_count)

            span.set_status("OK")
            return {
                'success': True,
                'reset_count': reset_count,
                'failed_keys': failed_keys,
                'message': f'Reset {reset_count} settings to defaults'
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error resetting settings: {e}", exc_info=True)
            span.set_status("ERROR", f"Database error: {str(e)}")
            record_metric('settings_reset', tags={'status': 'failed'}, value=1)
            raise ServiceUnavailableError(
                message="Settings service unavailable",
                code="SETTINGS_SERVICE_UNAVAILABLE"
            )

        except Exception as e:
            logger.error(f"Unexpected error resetting settings: {e}", exc_info=True)
            span.set_status("ERROR", f"Unexpected error: {str(e)}")
            record_metric('settings_reset', tags={'status': 'failed'}, value=1)
            raise

        finally:
            span.end()

    @staticmethod
    @lru_cache(maxsize=128)
    def is_feature_enabled(feature_key: str,
                          default: bool = False) -> bool:
        """
        Check if a feature is enabled with caching

        Args:
            feature_key: Setting key to check
            default: Default value if setting not found

        Returns:
            Boolean indicating if feature is enabled
        """
        try:
            # Try cache first
            cache_key = f"{SettingsService.CACHE_PREFIX}:feature:{feature_key}"
            cached = get_cached(cache_key)

            if cached is not None:
                return bool(cached)

            # Get from database
            value = get_setting(feature_key, default)

            # Cache result
            set_cached(cache_key, bool(value), timeout=SettingsService.CACHE_TTL)

            return bool(value)

        except Exception as e:
            logger.error(f"Error checking feature {feature_key}: {e}")
            return default

    @staticmethod
    def get_feature_config(feature_key: str,
                          default: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get configuration for a feature

        Args:
            feature_key: Setting key
            default: Default value

        Returns:
            Feature configuration dictionary
        """
        try:
            config = get_setting(feature_key, default or {})

            # Ensure it's a dict
            if not isinstance(config, dict):
                return default or {}

            return config

        except Exception as e:
            logger.error(f"Error getting feature config {feature_key}: {e}")
            return default or {}

    @staticmethod
    @monitor_endpoint("get_operational_status")
    def get_operational_status() -> Dict[str, Any]:
        """
        Get comprehensive operational status for dashboard

        Returns:
            Dict with operational status
        """
        try:
            # Get critical settings
            module_enabled = SettingsService.is_feature_enabled('transport_module_enabled', True)
            maintenance_mode = SettingsService.is_feature_enabled('maintenance_mode', False)
            environment = get_setting('environment', 'development')

            # Check critical features
            critical_features = [
                'transport_module_enabled',
                'provider_onboarding_enabled',
                'booking_system_enabled'
            ]

            critical_features_ok = all(
                SettingsService.is_feature_enabled(feature, True)
                for feature in critical_features
            )

            # Check integrations
            integrations = {
                'external_platforms': SettingsService.is_feature_enabled('external_integrations_enabled', False),
                'payment_gateway': SettingsService.is_feature_enabled('payment_processing_enabled', False),
                'mock_payments': SettingsService.is_feature_enabled('mock_payments_enabled', True)
            }

            # Check safety features
            safety_features = {
                'live_tracking': SettingsService.is_feature_enabled('enable_live_tracking', False),
                'sos_button': SettingsService.is_feature_enabled('sos_button_enabled', False),
                'data_encryption': SettingsService.is_feature_enabled('data_encryption_enabled', False)
            }

            # Check intelligence features
            intelligence_features = {
                'demand_forecasting': SettingsService.is_feature_enabled('demand_forecasting_enabled', False),
                'contingency_plans': SettingsService.is_feature_enabled('contingency_planning_enabled', False),
                'promotion_engine': SettingsService.is_feature_enabled('promotion_engine_enabled', True),
                'dynamic_pricing': SettingsService.is_feature_enabled('dynamic_pricing_enabled', False)
            }

            # Check performance features
            performance_features = {
                'caching': SettingsService.is_feature_enabled('caching_enabled', True),
                'rate_limiting': SettingsService.is_feature_enabled('rate_limiting_enabled', False),
                'monitoring': SettingsService.is_feature_enabled('monitoring_enabled', False)
            }

            # Calculate health score
            health_score = SettingsService._calculate_health_score(
                critical_features_ok=critical_features_ok,
                integrations=integrations,
                safety_features=safety_features,
                intelligence_features=intelligence_features,
                performance_features=performance_features
            )

            status = {
                'module_enabled': module_enabled,
                'maintenance_mode': maintenance_mode,
                'environment': environment,
                'critical_features_ok': critical_features_ok,
                'health_score': health_score,
                'integrations': integrations,
                'safety_features': safety_features,
                'intelligence_features': intelligence_features,
                'performance_features': performance_features,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }

            # Record metrics
            record_metric('operational_status_checked', value=1)

            return status

        except Exception as e:
            logger.error(f"Error getting operational status: {e}", exc_info=True)
            record_metric('operational_status_checked', tags={'status': 'failed'}, value=1)

            # Return minimal status on error
            return {
                'module_enabled': False,
                'maintenance_mode': True,
                'environment': 'unknown',
                'critical_features_ok': False,
                'health_score': 0,
                'integrations': {},
                'safety_features': {},
                'intelligence_features': {},
                'performance_features': {},
                'last_updated': datetime.now(timezone.utc).isoformat(),
                'error': str(e)
            }

    @staticmethod
    @monitor_endpoint("toggle_module")
    @rate_limit("toggle_module", limit=5, period=300)
    @require_permission('settings:toggle_module')
    def toggle_module(enabled: bool,
                     user_id: Optional[int] = None,
                     request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Toggle transport module on/off

        Args:
            enabled: Whether to enable the module
            user_id: User performing the action
            request_id: Unique request ID

        Returns:
            Dict with result
        """
        try:
            success = update_setting(
                key='transport_module_enabled',
                value=enabled,
                modified_by=user_id
            )

            if success:
                # Create audit log
                audit_log(
                    action='module_toggled',
                    entity_type='module',
                    user_id=user_id,
                    details={
                        'enabled': enabled,
                        'request_id': request_id
                    },
                    request_id=request_id
                )

                # Invalidate cache
                invalidate_cache_pattern(f"{SettingsService.CACHE_PREFIX}:*")

                # Record metrics
                record_metric('module_toggled', tags={'enabled': enabled}, value=1)

                return {
                    'success': True,
                    'message': f'Module {"enabled" if enabled else "disabled"} successfully',
                    'enabled': enabled
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to toggle module',
                    'enabled': not enabled
                }

        except Exception as e:
            logger.error(f"Error toggling module: {e}", exc_info=True)
            record_metric('module_toggled', tags={'status': 'failed'}, value=1)
            raise

    @staticmethod
    @monitor_endpoint("toggle_maintenance")
    @rate_limit("toggle_maintenance", limit=10, period=300)
    @require_permission('settings:toggle_maintenance')
    def toggle_maintenance(enabled: bool,
                          user_id: Optional[int] = None,
                          request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Toggle maintenance mode

        Args:
            enabled: Whether to enable maintenance mode
            user_id: User performing the action
            request_id: Unique request ID

        Returns:
            Dict with result
        """
        try:
            success = update_setting(
                key='maintenance_mode',
                value=enabled,
                modified_by=user_id
            )

            if success:
                # Create audit log
                audit_log(
                    action='maintenance_toggled',
                    entity_type='maintenance',
                    user_id=user_id,
                    details={
                        'enabled': enabled,
                        'request_id': request_id
                    },
                    request_id=request_id
                )

                # Invalidate cache
                invalidate_cache_pattern(f"{SettingsService.CACHE_PREFIX}:*")

                # Record metrics
                record_metric('maintenance_toggled', tags={'enabled': enabled}, value=1)

                return {
                    'success': True,
                    'message': f'Maintenance mode {"enabled" if enabled else "disabled"}',
                    'enabled': enabled
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to toggle maintenance mode',
                    'enabled': not enabled
                }

        except Exception as e:
            logger.error(f"Error toggling maintenance mode: {e}", exc_info=True)
            record_metric('maintenance_toggled', tags={'status': 'failed'}, value=1)
            raise

    #  Get a single setting value
    @staticmethod
    def get_setting(key: str, default: Any = None) -> Any:
        """
        Get a single setting value
        Args:
            key: Setting key
            default: Default value if not found
        Returns:
            Setting value
        """
        return get_setting(key, default)  # This uses your model's get_setting

    @staticmethod
    @monitor_endpoint("export_settings")
    @rate_limit("export_settings", limit=20, period=3600)
    @require_permission('settings:export')
    def export_settings(include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Export all settings to JSON format

        Args:
            include_sensitive: Include sensitive settings

        Returns:
            Dict with exported settings
        """
        try:
            # Get all settings
            settings = SettingsService.get_all_settings(
                include_advanced=True,
                include_sensitive=include_sensitive
            )

            # Filter out metadata
            exported = {}
            for setting in settings:
                if 'value' in setting:
                    exported[setting['key']] = setting['value']

            # Create export metadata
            metadata = {
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'count': len(exported),
                'include_sensitive': include_sensitive,
                'environment': get_setting('environment', 'unknown'),
                'version': SettingsService.CACHE_VERSION
            }

            # Record metrics
            record_metric('settings_exported', tags={'count': len(exported)}, value=1)

            return {
                'success': True,
                'settings': exported,
                'metadata': metadata
            }

        except Exception as e:
            logger.error(f"Error exporting settings: {e}", exc_info=True)
            record_metric('settings_exported', tags={'status': 'failed'}, value=1)
            raise

    @staticmethod
    @monitor_endpoint("import_settings")
    @rate_limit("import_settings", limit=10, period=3600)
    @require_permission('settings:import')
    def import_settings(settings_data: Dict[str, Any],
                       overwrite: bool = False,
                       user_id: Optional[int] = None,
                       request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Import settings from JSON data

        Args:
            settings_data: Settings data to import
            overwrite: Whether to overwrite existing settings
            user_id: User performing import
            request_id: Unique request ID

        Returns:
            Dict with import result
        """
        span = start_span("import_settings")
        span.set_attribute("settings.count", len(settings_data))

        try:
            imported_count = 0
            skipped_count = 0
            failed_keys = []

            for key, value in settings_data.items():
                try:
                    # Check if setting exists
                    setting = TransportSetting.query.filter_by(
                        key=key,
                        is_deleted=False
                    ).first()

                    if setting:
                        if not overwrite:
                            skipped_count += 1
                            continue

                        # Check permissions for sensitive settings
                        if not setting.is_public and not g.user.has_permission('settings:edit_sensitive'):
                            failed_keys.append({
                                'key': key,
                                'error': 'Insufficient permissions'
                            })
                            continue

                    # Validate value if setting exists
                    if setting:
                        validation_result = SettingsService._validate_setting_value(
                            setting=setting,
                            value=value
                        )

                        if not validation_result.valid:
                            failed_keys.append({
                                'key': key,
                                'error': 'Validation failed',
                                'details': validation_result.errors
                            })
                            continue

                        value = validation_result.normalized_value

                    # Update or create setting
                    if setting:
                        success = update_setting(
                            key=key,
                            value=value,
                            modified_by=user_id
                        )
                    else:
                        # Create new setting
                        new_setting = TransportSetting(
                            key=key,
                            value=value,
                            name=key.replace('_', ' ').title(),
                            description=f'Imported setting: {key}',
                            category='general',
                            data_type=SettingsService._infer_data_type(value),
                            is_public=False,
                            is_advanced=True,
                            requires_restart=True
                        )
                        db.session.add(new_setting)
                        db.session.commit()
                        success = True

                    if success:
                        imported_count += 1
                    else:
                        failed_keys.append({
                            'key': key,
                            'error': 'Import failed'
                        })

                except Exception as e:
                    logger.error(f"Error importing setting {key}: {e}")
                    failed_keys.append({
                        'key': key,
                        'error': str(e)
                    })

            # Create audit log
            if imported_count > 0:
                audit_log(
                    action='settings_imported',
                    entity_type='settings',
                    user_id=user_id,
                    details={
                        'imported_count': imported_count,
                        'skipped_count': skipped_count,
                        'failed_count': len(failed_keys),
                        'overwrite': overwrite,
                        'request_id': request_id
                    },
                    request_id=request_id
                )

            # Invalidate cache
            invalidate_cache_pattern(f"{SettingsService.CACHE_PREFIX}:*")

            # Record metrics
            record_metric(
                'settings_imported',
                tags={
                    'imported_count': imported_count,
                    'overwrite': overwrite
                },
                value=imported_count
            )

            span.set_status("OK")
            return {
                'success': True,
                'imported_count': imported_count,
                'skipped_count': skipped_count,
                'failed_keys': failed_keys,
                'message': f'Imported {imported_count} settings successfully'
            }

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error importing settings: {e}", exc_info=True)
            span.set_status("ERROR", f"Database error: {str(e)}")
            record_metric('settings_imported', tags={'status': 'failed'}, value=1)
            raise ServiceUnavailableError(
                message="Settings import failed",
                code="IMPORT_FAILED"
            )

        except Exception as e:
            db.session.rollback()
            logger.error(f"Unexpected error importing settings: {e}", exc_info=True)
            span.set_status("ERROR", f"Unexpected error: {str(e)}")
            record_metric('settings_imported', tags={'status': 'failed'}, value=1)
            raise

        finally:
            span.end()

    # ===========================================================================
    # PRIVATE HELPER METHODS
    # ===========================================================================

    @staticmethod
    def _validate_setting_value(setting: TransportSetting,
                               value: Any) -> SettingValidationResult:
        """
        Validate setting value based on data type and rules

        Args:
            setting: Setting object
            value: Value to validate

        Returns:
            SettingValidationResult
        """
        errors = []
        warnings = []
        normalized_value = value

        try:
            # Check data type
            if setting.data_type == 'boolean':
                if not isinstance(value, bool):
                    if isinstance(value, str):
                        value_lower = value.lower()
                        if value_lower in ('true', '1', 'yes', 'on'):
                            normalized_value = True
                        elif value_lower in ('false', '0', 'no', 'off'):
                            normalized_value = False
                        else:
                            errors.append(f"Invalid boolean value: {value}")
                    elif isinstance(value, (int, float)):
                        normalized_value = bool(value)
                    else:
                        errors.append(f"Invalid boolean type: {type(value)}")

            elif setting.data_type == 'integer':
                try:
                    normalized_value = int(value)
                except (ValueError, TypeError):
                    errors.append(f"Invalid integer value: {value}")

            elif setting.data_type == 'decimal':
                try:
                    normalized_value = Decimal(str(value))
                except (ValueError, TypeError):
                    errors.append(f"Invalid decimal value: {value}")

            elif setting.data_type == 'string':
                if not isinstance(value, str):
                    normalized_value = str(value)

            elif setting.data_type == 'json':
                if isinstance(value, str):
                    try:
                        normalized_value = json.loads(value)
                    except json.JSONDecodeError as e:
                        errors.append(f"Invalid JSON: {str(e)}")
                elif not isinstance(value, (dict, list, str, int, float, bool, type(None))):
                    errors.append(f"Invalid JSON type: {type(value)}")

            # Check allowed values
            if setting.allowed_values and normalized_value not in setting.allowed_values:
                errors.append(f"Value not in allowed values: {setting.allowed_values}")

            # Apply validation rules
            if setting.validation_rules:
                rules = setting.validation_rules

                # Min/Max for numbers
                if setting.data_type in ('integer', 'decimal'):
                    if 'min' in rules and normalized_value < rules['min']:
                        errors.append(f"Value must be >= {rules['min']}")
                    if 'max' in rules and normalized_value > rules['max']:
                        errors.append(f"Value must be <= {rules['max']}")

                # Min/Max length for strings
                if setting.data_type == 'string' and isinstance(normalized_value, str):
                    if 'min_length' in rules and len(normalized_value) < rules['min_length']:
                        errors.append(f"Length must be >= {rules['min_length']}")
                    if 'max_length' in rules and len(normalized_value) > rules['max_length']:
                        errors.append(f"Length must be <= {rules['max_length']}")

                # Pattern matching for strings
                if setting.data_type == 'string' and 'pattern' in rules:
                    import re
                    if not re.match(rules['pattern'], normalized_value):
                        errors.append(f"Value must match pattern: {rules['pattern']}")

            # Check for warnings
            if setting.requires_restart:
                warnings.append("Change requires system restart")

            if not setting.is_public:
                warnings.append("This is a sensitive setting")

            return SettingValidationResult(
                valid=len(errors) == 0,
                errors=errors,
                normalized_value=normalized_value,
                warnings=warnings
            )

        except Exception as e:
            logger.error(f"Validation error for setting {setting.key}: {e}")
            errors.append(f"Validation error: {str(e)}")
            return SettingValidationResult(
                valid=False,
                errors=errors,
                normalized_value=value,
                warnings=warnings
            )

    @staticmethod
    def _infer_data_type(value: Any) -> str:
        """Infer data type from value"""
        if isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, int):
            return 'integer'
        elif isinstance(value, (float, Decimal)):
            return 'decimal'
        elif isinstance(value, str):
            return 'string'
        elif isinstance(value, (dict, list)):
            return 'json'
        else:
            return 'string'

    @staticmethod
    def _calculate_health_score(**kwargs) -> int:
        """Calculate system health score (0-100)"""
        score = 100

        # Deduct for critical issues
        if not kwargs.get('critical_features_ok', True):
            score -= 40

        # Deduct for missing safety features
        safety_features = kwargs.get('safety_features', {})
        if not any(safety_features.values()):
            score -= 20

        # Deduct for missing payment integration
        integrations = kwargs.get('integrations', {})
        if not integrations.get('payment_gateway', False):
            score -= 10

        # Add for intelligence features
        intelligence_features = kwargs.get('intelligence_features', {})
        if any(intelligence_features.values()):
            score += 10

        # Add for performance features
        performance_features = kwargs.get('performance_features', {})
        if all(performance_features.values()):
            score += 10

        # Ensure score is between 0 and 100
        return max(0, min(100, score))

    @staticmethod
    def _get_cache_key(key: str) -> str:
        """Get cache key for setting"""
        return f"{SettingsService.CACHE_PREFIX}:{SettingsService.CACHE_VERSION}:{key}"


# ===========================================================================
# FEATURE GATE DECORATORS
# ===========================================================================

def feature_enabled(feature_key: str,
                   default: bool = False,
                   raise_exception: bool = True):
    """
    Decorator to enable/disable features at runtime

    Args:
        feature_key: Setting key to check
        default: Default value if setting not found
        raise_exception: Whether to raise exception or return mock response
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if SettingsService.is_feature_enabled(feature_key, default):
                return func(*args, **kwargs)
            else:
                if raise_exception:
                    raise ServiceUnavailableError(
                        message=f"Feature {feature_key} is currently disabled",
                        code="FEATURE_DISABLED",
                        feature_key=feature_key
                    )
                else:
                    # Return mock response
                    current_app.logger.info(f"Feature {feature_key} is disabled, returning mock response")
                    return {
                        'success': False,
                        'message': f'Feature {feature_key} is currently disabled',
                        'feature_disabled': True,
                        'mock_response': True
                    }
        return wrapper
    return decorator


def development_only(func):
    """Decorator for features only available in development"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        environment = get_setting('environment', 'development')
        if environment == 'development':
            return func(*args, **kwargs)
        else:
            current_app.logger.warning(
                f"Attempted to use development-only feature in {environment}"
            )
            raise PermissionError(
                message=f"This feature is only available in development mode (current: {environment})",
                code="DEVELOPMENT_ONLY"
            )
    return wrapper


def production_only(func):
    """Decorator for features only available in production"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        environment = get_setting('environment', 'development')
        if environment == 'production':
            return func(*args, **kwargs)
        else:
            current_app.logger.warning(
                f"Attempted to use production-only feature in {environment}"
            )
            raise PermissionError(
                message=f"This feature is only available in production mode (current: {environment})",
                code="PRODUCTION_ONLY"
            )
    return wrapper


# ===========================================================================
# SERVICE INITIALIZATION
# ===========================================================================

def init_settings_service():
    """Initialize settings service"""
    from app.core.di import Container
    container = Container()

    container.register(
        'settings_service',
        SettingsService,
        singleton=True
    )

    # Register decorators
    container.register(
        'feature_enabled',
        feature_enabled,
        singleton=False
    )

    container.register(
        'development_only',
        development_only,
        singleton=False
    )

    container.register(
        'production_only',
        production_only,
        singleton=False
    )

    logger.info("✅ Settings Service Initialized (Production Mode)")

    return SettingsService


# ===========================================================================
# CONTEXT PROCESSORS
# ===========================================================================

def settings_context_processor():
    """Make settings available in templates"""
    return {
        'get_setting': get_setting,
        'is_feature_enabled': SettingsService.is_feature_enabled,
        'get_operational_status': SettingsService.get_operational_status
    }

# ------------------------
# Singleton getter (module-level)
# ------------------------
# Module-level singleton
_settings_instance: SettingsService | None = None

def get_settings_service() -> SettingsService:
    """Return the singleton SettingsService instance"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = SettingsService()
    return _settings_instance
