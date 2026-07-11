"""Template context processors for module isolation"""
from datetime import datetime

def register_template_helpers(app):
    """Register safe template helpers - call once in create_app()"""
    
    # Import here to avoid circular imports
    from app.utils.module_guard import safe_url, module_enabled, get_module_status
    
    @app.context_processor
    def inject_module_helpers():
        return {
            'safe_url': safe_url,
            'module_enabled': module_enabled,
            'module_status': get_module_status(),
            'now': datetime.now,
        }
    
    app.logger.info("✅ Template helpers registered (safe_url, module_enabled)")
