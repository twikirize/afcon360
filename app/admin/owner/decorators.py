# app/admin/owner/decorators.py
"""
Owner-specific decorators
FIXED: Safe transaction handling
"""

from functools import wraps
from flask import session, redirect, url_for, flash, request, abort, current_app
from flask_login import current_user
import logging
from datetime import datetime, timedelta
from app.extensions import db

logger = logging.getLogger(__name__)


def owner_required(f):
    """Require owner role - highest privilege level with safe transaction handling"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in first', 'warning')
            return redirect(url_for('auth_routes.login', next=request.url))

        # CRITICAL: Ensure clean session state before role check
        # Rollback any aborted transaction safely
        try:
            db.session.rollback()
        except Exception as e:
            # Session may not exist or be in a bad state
            # Try to create new session
            try:
                db.session.remove()
            except:
                pass

        # Check if user has owner role safely
        try:
            is_owner = False

            # Try multiple methods to check owner status safely
            # Method 1: Check via has_role method if available
            if hasattr(current_user, 'has_role'):
                try:
                    is_owner = current_user.has_role('owner')
                except Exception:
                    pass

            # Method 2: Check roles relationship safely
            if not is_owner and hasattr(current_user, 'roles'):
                try:
                    for ur in current_user.roles:
                        if ur.role and ur.role.name == 'owner':
                            is_owner = True
                            break
                except Exception as e:
                    logger.warning(f"Error iterating roles: {e}")

            # Method 3: Direct database check (last resort)
            if not is_owner:
                from app.identity.models.user import User
                from app.identity.models.roles_permission import Role
                try:
                    user = User.query.get(current_user.id)
                    if user:
                        owner_role = Role.query.filter_by(name='owner', scope='global').first()
                        if owner_role:
                            from app.identity.models.user import UserRole
                            is_owner = UserRole.query.filter_by(
                                user_id=user.id,
                                role_id=owner_role.id
                            ).first() is not None
                except Exception as e:
                    logger.error(f"Direct owner check failed: {e}")

            if not is_owner:
                logger.warning(f"Non-owner attempted access: {current_user.id}")
                abort(403)

        except Exception as e:
            logger.error(f"Error checking owner role: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass
            abort(403)

        return f(*args, **kwargs)

    return decorated_function


def owner_password_confirm_required(f):
    """Require recent password confirmation for danger zone"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('owner_password_confirmed_at'):
            flash('Please confirm your password to continue', 'warning')
            return redirect(url_for('admin.owner.confirm_password', next=request.url))

        # Check if confirmation is recent (<5 minutes)
        try:
            confirmed_at = datetime.fromisoformat(session['owner_password_confirmed_at'])
            if datetime.utcnow() - confirmed_at > timedelta(minutes=5):
                session.pop('owner_password_confirmed_at', None)
                flash('Password confirmation expired', 'warning')
                return redirect(url_for('admin.owner.confirm_password', next=request.url))
        except (ValueError, TypeError):
            session.pop('owner_password_confirmed_at', None)
            return redirect(url_for('admin.owner.confirm_password', next=request.url))

        return f(*args, **kwargs)

    return decorated_function
