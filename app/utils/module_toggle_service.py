"""Database-backed module toggle management."""
from __future__ import annotations

import json
import logging
from typing import Dict, Optional
from flask import current_app

logger = logging.getLogger(__name__)


class ModuleToggleService:
    """
    Manage module enable/disable flags with the database as source of truth.
    """

    SETTINGS_KEY = "MODULE_FLAGS"

    @classmethod
    def _fetch_stored_flags(cls) -> Dict[str, bool]:
        """Fetch persisted module flags from SystemConfig."""
        try:
            from app.models.system_config import SystemConfig
            stored_val = SystemConfig.get(cls.SETTINGS_KEY)
            if stored_val:
                return json.loads(stored_val)
            return {}
        except Exception as e:
            logger.debug(f"Failed to fetch stored flags: {e}")
            return {}

    @classmethod
    def get_flags(cls) -> Dict[str, bool]:
        """Return current module flags (defaults merged with overrides)."""
        overrides = cls._fetch_stored_flags()
        defaults = dict(current_app.config.get("MODULE_FLAGS", {}))
        defaults.update(overrides)
        return defaults

    @classmethod
    def load_overrides_into_app(cls) -> None:
        """Sync DB flags to app config."""
        try:
            merged = cls.get_flags()
            current_app.config["MODULE_FLAGS"] = merged
            for module_name, enabled in merged.items():
                current_app.config[f"{module_name.upper()}_ENABLED"] = bool(enabled)
        except Exception as e:
            logger.warning(f"Load module overrides failed: {e}")

    @classmethod
    def is_enabled(cls, module_name: str) -> bool:
        """Check if a module is enabled."""
        flags = cls.get_flags()
        return flags.get(module_name.strip().lower(), True)

    @classmethod
    def is_module_enabled(cls, module_name: str) -> bool:
        """Alias for is_enabled."""
        return cls.is_enabled(module_name)

    @classmethod
    def set_flag(cls, module: str, enabled: bool, updated_by: Optional[int] = None) -> Dict[str, bool]:
        """Update a module flag."""
        module = module.strip().lower()
        from app.extensions import db
        from app.models.system_config import SystemConfig
        
        overrides = cls._fetch_stored_flags()
        overrides[module] = bool(enabled)
        
        SystemConfig.set(
            key=cls.SETTINGS_KEY,
            value=json.dumps(overrides),
            value_type='json',
            description="Module flags",
            updated_by=updated_by
        )
        db.session.commit()
        cls.load_overrides_into_app()
        return current_app.config["MODULE_FLAGS"]
