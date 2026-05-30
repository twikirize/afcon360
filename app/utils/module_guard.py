"""Module isolation utilities - prevents crashes from disabled modules"""
from flask import current_app, url_for, has_request_context, g
import logging
import importlib
import json
from functools import wraps
from typing import Optional, Any, Dict

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
    
    try:
        # Check if we're in app context
        if not has_request_context() and not current_app:
            return '#'
        
        # Check if this is a module endpoint and if module is disabled
        if '.' in endpoint:
            module_name = endpoint.split('.')[0]
            if not module_enabled(module_name):
                # Return a special URL that will show the disabled module page
                return f'/module-disabled/{module_name}'
        
        return url_for(endpoint, **kwargs)
    except Exception as e:
        # Only log in debug mode to avoid spam
        if current_app and current_app.debug:
            logger.debug(f"safe_url: '{endpoint}' not found - {e}")
        return '#'

def module_enabled(module_name: str) -> bool:
    """
    Check if a module is enabled - reads from database-backed service.
    Falls back to config if service unavailable.
    Uses Redis caching (60s TTL) + request-scoped caching for efficiency.
    """
    # Load flags once per request if not already cached
    if not getattr(g, "module_flags_loaded", False):
        try:
            from app.services.module_toggle_service import ModuleToggleService
            # Try Redis cache first
            try:
                from app.extensions import redis_client
                cached_flags = redis_client.get('module_flags')
                if cached_flags:
                    g.module_flags = json.loads(cached_flags)
                    logger.debug("Module flags loaded from Redis cache")
                else:
                    # Cache miss - load from DB
                    g.module_flags = ModuleToggleService.get_flags()
                    redis_client.set('module_flags', json.dumps(g.module_flags), ex=60)  # 60s TTL
                    logger.debug("Module flags loaded from DB, cached in Redis")
            except (ImportError, RuntimeError):
                # Redis not available, load directly
                g.module_flags = ModuleToggleService.get_flags()
                logger.debug("Module flags loaded from DB (Redis unavailable)")
        except (ImportError, RuntimeError) as e:
            logger.debug(f"ModuleToggleService unavailable, using config: {e}")
            try:
                if has_request_context() and current_app:
                    g.module_flags = current_app.config.get('MODULE_FLAGS', {})
                else:
                    g.module_flags = {}
            except (RuntimeError, AttributeError):
                g.module_flags = {}
        
        g.module_flags_loaded = True
    
    # Return cached result
    return getattr(g, 'module_flags', {}).get(module_name, False)

def safe_import(module_path: str, fallback: Any = None) -> Optional[Any]:
    """Safely import a module, return fallback on failure"""
    try:
        return importlib.import_module(module_path)
    except ImportError as e:
        logger.debug(f"safe_import failed for {module_path}: {e}")
        return fallback
    except Exception as e:
        logger.warning(f"Unexpected error importing {module_path}: {e}")
        return fallback

def get_module_blueprint(module_name: str, blueprint_name: str = None):
    """
    Safely get a module's blueprint if module is enabled.
    Returns None if module disabled or blueprint not found.
    """
    if not module_enabled(module_name):
        return None
    
    blueprint_name = blueprint_name or module_name
    try:
        module = safe_import(f'app.{module_name}')
        if module and hasattr(module, f'{blueprint_name}_bp'):
            return getattr(module, f'{blueprint_name}_bp')
    except Exception as e:
        logger.warning(f"Failed to get blueprint for {module_name}: {e}")
    return None

def require_module_enabled(module_name: str):
    """
    Decorator that returns 404 for disabled modules.
    More strict than module_enabled_required - no redirects.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not module_enabled(module_name):
                from flask import abort, render_template
                # Return 404 with module disabled template
                return render_template('module_disabled.html', module=module_name), 404
            return func(*args, **kwargs)
        return wrapper
    return decorator

def get_disabled_module_url(module_name: str) -> str:
    """
    Get the URL for a disabled module's information page.
    """
    return f'/module-disabled/{module_name}'

def get_module_status() -> Dict[str, bool]:
    """Get all module flags - safe to call anywhere"""
    try:
        if has_request_context() and current_app:
            return current_app.config.get('MODULE_FLAGS', {})
        else:
            # Return empty dict if no app context
            return {}
    except (RuntimeError, AttributeError):
        return {}
