#app/admin/owner/decorators.py
"""
Owner-specific decorators
"""

from functools import wraps
from flask import session, redirect, url_for, flash, request, abort
from flask_login import current_user
import logging

logger = logging.getLogger(__name__)


def owner_required(f):
    """Require owner role - highest privilege level"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in first', 'warning')
            return redirect(url_for('auth.login', next=request.url))

        # Check if user has owner role
        is_owner = False
        if hasattr(current_user, 'roles'):
            is_owner = any(getattr(ur.role, 'name', None) == 'owner'
                           for ur in current_user.roles)

        if not is_owner:
            logger.warning(f"Non-owner attempted access: {current_user.id}")
            abort(403)

        return f(*args, **kwargs)

    return decorated_function


def owner_password_confirm_required(f):
    """Require recent password confirmation for danger zone"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('owner_password_confirmed_at'):
            flash('Please confirm your password to continue', 'warning')
            return redirect(url_for('owner.confirm_password', next=request.url))

        # Check if confirmation is recent (<5 minutes)
        from datetime import datetime, timedelta
        confirmed_at = datetime.fromisoformat(session['owner_password_confirmed_at'])
        if datetime.utcnow() - confirmed_at > timedelta(minutes=5):
            session.pop('owner_password_confirmed_at', None)
            flash('Password confirmation expired', 'warning')
            return redirect(url_for('owner.confirm_password', next=request.url))

        return f(*args, **kwargs)

    return decorated_function