"""Routes for handling disabled module pages"""
from flask import Blueprint, render_template, abort
from app.utils.module_guard import module_enabled

# Create blueprint
module_disabled_bp = Blueprint('module_disabled', __name__)

@module_disabled_bp.route('/module-disabled/<module_name>')
def module_disabled_page(module_name):
    """
    Show a user-friendly page when a disabled module is accessed.
    """
    # Validate module name
    valid_modules = ['wallet', 'tourism', 'transport', 'accommodation', 'events', 'tournament', 'agents']
    
    if module_name not in valid_modules:
        abort(404)
    
    # If module is actually enabled, redirect to the module
    if module_enabled(module_name):
        # Try to redirect to the module's home page
        try:
            from flask import url_for, redirect
            if module_name == 'events':
                return redirect(url_for('events.list'))
            elif module_name == 'tourism':
                return redirect(url_for('tourism.home'))
            elif module_name == 'transport':
                return redirect(url_for('transport.home'))
            elif module_name == 'accommodation':
                return redirect(url_for('accommodation.guest_search'))
            elif module_name == 'wallet':
                return redirect(url_for('wallet.dashboard'))
            elif module_name == 'tournament':
                return redirect(url_for('tournament.home'))
            elif module_name == 'agents':
                return redirect(url_for('agents.home'))
        except:
            # If redirect fails, just show the page anyway
            pass
    
    return render_template('module_disabled.html', module_name=module_name)
