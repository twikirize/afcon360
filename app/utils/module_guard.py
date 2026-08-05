"""Module isolation utilities - prevents crashes from disabled modules"""
from flask import current_app, url_for, has_request_context, g, render_template
import logging
import importlib
import json
from functools import wraps
from typing import Optional, Any, Dict, Set

logger = logging.getLogger(__name__)

def safe_url(endpoint: str, **kwargs) -> str:
    """
    Safe url_for that handles disabled modules gracefully.
    - Returns disabled module URL if module is disabled
    - Returns '#' for completely missing endpoints
    This keeps navigation visible but handles clicks properly.
    """
    if not endpoint:
        return '#'

    # Callers sometimes pass an already-built path/URL instead of an endpoint
    # name. url_for() cannot build those and would raise, degrading to '#'.
    # A '#' is dangerous here: the dashboard pane router fetches data-pane-url
    # values, and fetch('#?_pane=1') resolves back to the current page, which
    # re-injects the whole dashboard into itself. Pass real paths through.
    if endpoint.startswith(('/', 'http://', 'https://')):
        return endpoint

    try:
        # Check if we're in app context
        if not has_request_context() and not current_app:
            return '#'
        
        # Check if this is a feature module endpoint and if that module is disabled.
        # Do not treat every dotted Flask endpoint as a feature module: blueprints
        # like admin, auth, profile, kyc, org, owner, auditor, compliance, support,
        # and moderator are core blueprints, not optional modules.
        if '.' in endpoint:
            module_name = endpoint.split('.')[0]
            if module_name in MODULE_REGISTRY and not module_enabled(module_name):
                # Return a special URL that will show the disabled module page
                return f'/module-disabled/{module_name}'
        
        return url_for(endpoint, **kwargs)
    except Exception as e:
        # Only log in debug mode to avoid spam
        if current_app and current_app.debug:
            logger.debug(f"safe_url: '{endpoint}' not found - {e}")
        return '#'

# --- REGISTRY ---
MODULE_REGISTRY: Set[str] = {
    "wallet", "transport", "accommodation",
    "tourism", "tournament", "events"
}

def module_enabled(module_name: str) -> bool:
    """
    Check if a module is enabled.
    Source of truth is current_app.config['MODULE_FLAGS'].
    """
    try:
        if has_request_context() and current_app:
            modules = current_app.config.get("MODULE_FLAGS", {})
            return bool(modules.get(module_name, False))
        return False
    except Exception:
        return False

def require_module_enabled(module_name: str):
    """
    Decorator that returns a 404 with the module_disabled template.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not module_enabled(module_name):
                return render_template('module_disabled.html', module=module_name), 404
            return func(*args, **kwargs)
        return wrapper
    return decorator

def get_module_status() -> Dict[str, Dict[str, bool]]:
    """
    Dictionary format for templates: {'wallet': {'enabled': True}}
    """
    try:
        if has_request_context() and current_app:
            raw_flags = current_app.config.get('MODULE_FLAGS', {})
            return {k: {'enabled': bool(v)} for k, v in raw_flags.items()}
        return {}
    except Exception:
        return {}

def safe_import(module_path: str, fallback: Any = None) -> Optional[Any]:
    try:
        return importlib.import_module(module_path)
    except Exception:
        return fallback

def get_module_blueprint(module_name: str, blueprint_name: str = None):
    if not module_enabled(module_name):
        return None
    blueprint_name = blueprint_name or module_name
    module = safe_import(f'app.{module_name}')
    if module and hasattr(module, f'{blueprint_name}_bp'):
        return getattr(module, f'{blueprint_name}_bp')
    return None

def init_realtime_invalidation(app):
    """No-op for rollback stability."""
    pass

def invalidate_module_cache():
    """No-op for rollback stability."""
    pass
