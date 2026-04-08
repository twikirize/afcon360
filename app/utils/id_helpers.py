"""
ID Helper Utilities - Enforce correct ID usage across the app
"""

import uuid
from functools import wraps
from flask import abort, request, jsonify, session
from flask_login import current_user


class IDType:
    """Constants for ID types"""
    INTERNAL = 'internal'  # BIGINT - for database FKs
    EXTERNAL = 'external'  # UUID - for public exposure


def ensure_internal_id(id_value):
    """Validate that an ID is a proper internal BIGINT"""
    if isinstance(id_value, int):
        return id_value
    if isinstance(id_value, str) and id_value.isdigit():
        return int(id_value)
    raise TypeError(f"Expected internal ID (BIGINT), got {type(id_value)}: {id_value}")


def ensure_external_id(id_value):
    """Validate that an ID is a proper external UUID"""
    try:
        uuid.UUID(str(id_value))
        return str(id_value)
    except:
        raise TypeError(f"Expected external ID (UUID), got: {id_value}")


def route_uses_public_id(f):
    """
    Decorator for routes that should use public UUID in URL

    Example:
    @app.route('/user/<public_id>')
    @route_uses_public_id
    def user_profile(public_id):
        user = User.get_by_public_id(public_id)
    """
    @wraps(f)
    def decorated_function(public_id, *args, **kwargs):
        # Validate it's a proper UUID
        try:
            ensure_external_id(public_id)
        except TypeError:
            abort(404)
        return f(public_id, *args, **kwargs)
    return decorated_function


def get_current_internal_id():
    """Use this for ALL foreign key assignments"""
    if current_user.is_authenticated:
        return current_user.id
    return session.get('user_internal_id')


def get_current_public_id():
    """Use this for ALL URL generation and API responses"""
    if current_user.is_authenticated:
        # Assuming User model has 'user_id' as the UUID-style string
        return getattr(current_user, 'user_id', None)
    return session.get('user_public_id')


class SessionManager:
    """Manages user session data with clear ID separation"""

    @staticmethod
    def set_user_session(user):
        """Store user in session with both IDs"""
        # Internal ID (for database operations)
        session['user_internal_id'] = user.id  # BIGINT

        # External ID (for public display, debugging)
        session['user_public_id'] = user.user_id  # UUID String (mapping from your User model)

    @staticmethod
    def get_internal_user_id():
        """Get internal BIGINT ID for database operations"""
        return get_current_internal_id()

    @staticmethod
    def get_public_user_id():
        """Get public UUID for display/API responses"""
        return get_current_public_id()
