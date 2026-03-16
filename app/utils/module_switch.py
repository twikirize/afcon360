#app/utils/module_switch
"""
Simple module switch system that checks config before allowing access
"""
from flask import current_app, abort, redirect, url_for, flash
from flask_login import current_user
from functools import wraps


def module_enabled_required(module_name: str):
    """
    Decorator that checks if module is enabled in config.
    If disabled: shows message to admins, 404 to others.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            module_flags = current_app.config.get("MODULE_FLAGS", {})

            # Check if module is enabled
            if not module_flags.get(module_name, False):
                if current_user.is_authenticated:
                    # Show admin-friendly message to admins
                    if hasattr(current_user, 'has_global_role') and current_user.has_global_role('admin'):
                        flash(
                            f'{module_name.title()} module is disabled. '
                            f'Enable it in admin dashboard or set ENABLE_{module_name.upper()}=true in .env',
                            'warning'
                        )
                        return redirect(url_for('admin.super_dashboard'))
                    else:
                        # Regular users get simple message
                        flash(f'{module_name.title()} module is currently unavailable.', 'info')
                        return redirect(url_for('index'))
                else:
                    # Non-authenticated users get 404
                    abort(404)

            return func(*args, **kwargs)

        return wrapper

    return decorator


def check_module_enabled(module_name: str) -> bool:
    """
    Simple function to check if a module is enabled.
    Returns True/False without any redirects.
    """
    module_flags = current_app.config.get("MODULE_FLAGS", {})
    return module_flags.get(module_name, False)


def get_disabled_modules() -> list:
    """
    Get list of disabled modules.
    """
    module_flags = current_app.config.get("MODULE_FLAGS", {})
    return [name for name, enabled in module_flags.items() if not enabled]
