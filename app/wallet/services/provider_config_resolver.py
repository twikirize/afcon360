"""
Provider Configuration Resolver
Centralized configuration resolver for payment providers.
Replaces direct current_app.config access with database-backed configuration.
"""

from enum import Enum
from typing import Optional, Dict, Any
from flask import current_app

from app.extensions import db
from app.wallet.models.config import PaymentProviderConfig
from app.wallet.enums import PaymentProvider, PaymentMethod


class ProviderConfigResolver:
    """
    Resolves payment provider configuration from database with fallback to app config.
    
    Priority order:
    1. Enabled PaymentProviderConfig from database (for the requested provider and environment)
    2. Fallback to current_app.config (for pre-migration compatibility)
    
    Rules:
    - If a provider config exists in DB but is disabled, return None (never fall back to static config)
    - If no DB config exists, fall back to app config (pre-migration state)
    - If DB config exists but credentials fail to decrypt, fail securely
    """
    
    @staticmethod
    def get(provider: PaymentProvider, is_sandbox: bool = None) -> Optional[Dict[str, Any]]:
        """
        Get provider configuration.
        
        Args:
            provider: The payment provider enum
            is_sandbox: 'sandbox' or 'live' (defaults to app config PAYMENT_SANDBOX)
            
        Returns:
            Configuration dict or None if provider is explicitly disabled
            
        Raises:
            ValueError: If credentials cannot be decrypted
        """
        # Normalize environment
        if is_sandbox is None:
            is_sandbox = current_app.config.get('PAYMENT_SANDBOX', True)
        
        # Try to get from database first
        db_config = PaymentProviderConfig.get_active_config(provider.value, is_sandbox)
        
        if db_config:
            # Check if disabled or inactive
            if not db_config.is_enabled or not db_config.is_active:
                # Explicitly disabled in DB - never fall back to static config
                return None
            
            # Get credentials from DB (will raise if decryption fails)
            try:
                secret_key = db_config.secret_key
                public_key = db_config.public_key
                encryption_key = db_config.encryption_key
            except ValueError as e:
                # Decryption failed - fail securely
                current_app.logger.error(f"Failed to decrypt credentials for {provider.value}: {e}")
                raise ValueError(f"Cannot decrypt credentials for {provider.value}") from e
            
            if not secret_key:
                current_app.logger.warning(f"No secret key configured for {provider.value} in DB")
                return None
            
            # Build config from DB
            config = {
                'SECRET_KEY': secret_key,
                'PUBLIC_KEY': public_key,
                'ENCRYPTION_KEY': encryption_key,
                'WEBHOOK_URL': db_config.webhook_url,
                'WEBHOOK_SECRET': db_config.webhook_secret,
                'IS_SANDBOX': db_config.is_sandbox,
                'SUPPORTED_CURRENCIES': db_config.config_json.get('supported_currencies', []),
                'SUPPORTED_METHODS': db_config.config_json.get('supported_methods', []),
                'BASE_URL': db_config.config_json.get('base_url'),
                'SANDBOX_URL': db_config.config_json.get('sandbox_url'),
            }
            
            # Add provider-specific config
            config.update(db_config.config_json)
            
            return config
        
        # No DB config found - fall back to app config (pre-migration state)
        # This allows gradual migration without breaking existing deployments
        fallback_key = f'{provider.value.upper()}_CONFIG'
        app_config = current_app.config.get(fallback_key, {})
        
        if not app_config:
            current_app.logger.warning(f"No configuration found for {provider.value} (DB or app config)")
            return None
        
        # Add environment info
        app_config = dict(app_config)
        app_config['IS_SANDBOX'] = is_sandbox
        app_config['_SOURCE'] = 'app_config_fallback'
        
        return app_config
    
    @staticmethod
    def get_all_active() -> Dict[str, Dict[str, Any]]:
        """
        Get all active provider configurations.
        
        Returns:
            Dict mapping provider value to configuration
        """
        configs = {}
        for provider in PaymentProvider:
            config = ProviderConfigResolver.get(provider)
            if config:
                configs[provider.value] = config
        return configs
    
    @staticmethod
    def is_provider_available(provider: PaymentProvider) -> bool:
        """Check if a payment provider is configured and available."""
        config = ProviderConfigResolver.get(provider)
        return config is not None
    
    @staticmethod
    def get_provider_status() -> Dict[str, bool]:
        """Get status of all payment providers."""
        return {
            provider.value: ProviderConfigResolver.is_provider_available(provider)
            for provider in PaymentProvider
        }


# Convenience function for backward compatibility
def get_provider_config(provider: PaymentProvider) -> Optional[Dict[str, Any]]:
    """Get provider configuration using resolver."""
    return ProviderConfigResolver.get(provider)


def is_provider_available(provider: PaymentProvider) -> bool:
    """Check if provider is available."""
    return ProviderConfigResolver.is_provider_available(provider)


def get_available_providers(country_code: str = None) -> list:
    """Get available providers for a country (delegates to factory for country logic)."""
    from app.wallet.services.payment_gateway import PaymentGatewayFactory
    return PaymentGatewayFactory.get_available_providers(country_code)