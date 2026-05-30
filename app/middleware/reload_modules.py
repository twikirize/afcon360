"""Reload module flags before every request for instant toggle effect."""
# app/middleware/reload_modules.py

from flask import g


def init_module_reload(app):
    """Initialize module reload hooks."""

    @app.before_request
    def clear_module_flags():
        """Clear cached module flags before each request."""
        g.module_flags_loaded = False

    app.logger.info("✅ Module reload hooks initialized")
