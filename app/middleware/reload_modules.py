"""Reload module flags before every request for instant effect."""
from app.services.module_toggle_service import ModuleToggleService

def init_module_reload(app):
    """Initialize module reload hooks."""

    @app.before_request
    def refresh_module_flags():
        """Refresh module flags from DB before each request."""
        from flask import request as _req
        if _req.path.startswith('/static/'):
            return
        try:
            ModuleToggleService.load_overrides_into_app()
        except Exception:
            pass

    app.logger.info("✅ Module reload hooks initialized (Instant Effect)")
