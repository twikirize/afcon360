# app/fan/routes.py
# DEPRECATED REDIRECT SHELL
# Fan logic has moved:
#   Dashboard  → /user/dashboard       (user_bp)
#   Settings   → /user/settings/interests (user_bp)
#
# This file exists only to preserve old bookmarks and external links.
# Schedule for deletion: 3 months after deployment.
# Before deleting: verify zero traffic to /fan/* in server logs.

from flask import Blueprint, redirect, url_for

fan_bp = Blueprint('fan', __name__, url_prefix='/fan')


@fan_bp.route('/', endpoint='index')
@fan_bp.route('/dashboard', endpoint='dashboard')
def dashboard_redirect():
    """301 permanent redirect — old /fan/dashboard bookmarks."""
    return redirect(url_for('user.dashboard'), code=301)


@fan_bp.route('/profile', endpoint='profile')
def profile_redirect():
    """301 permanent redirect — old /fan/profile links."""
    return redirect(url_for('user.interests_settings'), code=301)


@fan_bp.route('/settings', endpoint='settings')
def settings_redirect():
    """301 permanent redirect — any /fan/settings links."""
    return redirect(url_for('user.interests_settings'), code=301)
