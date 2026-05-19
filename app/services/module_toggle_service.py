"""Database-backed module toggle management."""
from __future__ import annotations

from typing import Dict, Optional
import logging

from flask import current_app

logger = logging.getLogger(__name__)


class ModuleToggleService:
    """Manage module enable/disable flags with the database as source of truth."""

    SETTINGS_KEY = "MODULE_FLAGS"

    @classmethod
    def _fetch_stored_flags(cls) -> Dict[str, bool]:
        """Fetch persisted module flags from SystemSetting (JSON)."""
        try:
            from app.admin.owner.models import SystemSetting  # Local import to avoid circulars
        except Exception:
            return {}

        stored = SystemSetting.get(cls.SETTINGS_KEY, default={})
        return stored if isinstance(stored, dict) else {}

    @classmethod
    def _persist_flags(cls, flags: Dict[str, bool], updated_by: Optional[int] = None) -> None:
        """Persist module flags into SystemSetting as JSON."""
        try:
            from app.admin.owner.models import SystemSetting
        except Exception:
            return

        SystemSetting.set(
            key=cls.SETTINGS_KEY,
            value=flags,
            value_type="json",
            category="modules",
            description="Module enable/disable flags",
            updated_by=updated_by,
        )

    @classmethod
    def get_flags(cls, include_defaults: bool = True) -> Dict[str, bool]:
        """Return current module flags (defaults merged with overrides)."""
        overrides = cls._fetch_stored_flags()
        if not include_defaults:
            return overrides

        defaults = dict(current_app.config.get("MODULE_FLAGS", {}))
        defaults.update(overrides)
        return defaults

    @classmethod
    def load_overrides_into_app(cls) -> None:
        """Overlay stored flags onto the Flask app config."""
        merged = cls.get_flags(include_defaults=True)
        current_app.config["MODULE_FLAGS"] = merged

        # Keep legacy *_ENABLED keys in sync so existing checks keep working.
        for module_name, enabled in merged.items():
            legacy_key = f"{module_name.upper()}_ENABLED"
            current_app.config[legacy_key] = enabled

    @classmethod
    def set_flag(cls, module: str, enabled: bool, updated_by: Optional[int] = None) -> Dict[str, bool]:
        """Update a module flag and keep application config in sync."""
        module = module.strip().lower()
        if not module:
            raise ValueError("Module name is required")

        flags = cls.get_flags(include_defaults=False)
        flags[module] = bool(enabled)
        cls._persist_flags(flags, updated_by=updated_by)

        # Update in-memory config immediately for the current process
        merged = cls.get_flags(include_defaults=True)
        current_app.config["MODULE_FLAGS"] = merged
        current_app.config[f"{module.upper()}_ENABLED"] = bool(enabled)
        
        # Publish to Redis Pub/Sub for real-time updates across all instances
        try:
            from app.extensions import redis_client
            redis_client.client  # Trigger connection
            redis_client.publish('module_toggles', f'{module}:{enabled}')
            logger.info(f"Module toggle published to Redis Pub/Sub: {module}={enabled}")
            # Invalidate cache
            redis_client.delete('module_flags')
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.warning(f"Failed to publish module toggle to Redis Pub/Sub: {e}")
        
        return merged

    @classmethod
    def is_enabled(cls, module: str) -> bool:
        """Convenience helper."""
        return cls.get_flags().get(module.lower(), False)

    @classmethod
    def get_disabled_modules(cls) -> Dict[str, bool]:
        """Return modules explicitly disabled in overrides."""
        return {name: enabled for name, enabled in cls.get_flags().items() if not enabled}
