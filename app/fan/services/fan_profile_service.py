# app/fan/services/fan_profile_service.py
"""
Service layer for FanProfile operations.
All fan profile business logic lives here.
Routes and templates call this — never touch models directly.
"""

import json
from datetime import datetime, timezone
from app.extensions import db
from app.fan.models import FanProfile, UserDashboardContext


def get_fan_profile(user_id: int) -> FanProfile | None:
    """Return FanProfile if exists, else None."""
    return FanProfile.query.filter_by(user_id=user_id).first()


def get_dashboard_context(user_id: int) -> UserDashboardContext | None:
    return UserDashboardContext.query.filter_by(user_id=user_id).first()


def activate_fan_profile(user_id: int, favorite_teams=None, favorite_sports=None) -> FanProfile:
    """
    Create or re-activate a FanProfile for the given user.
    Called from Settings → Interests → Activate Fan Profile.
    """
    profile = FanProfile.query.filter_by(user_id=user_id).first()

    if profile:
        profile.activate()
        if favorite_teams is not None:
            profile.favorite_teams = json.dumps(favorite_teams)
        if favorite_sports is not None:
            profile.favorite_sports = json.dumps(favorite_sports)
    else:
        profile = FanProfile(
            user_id=user_id,
            is_active=True,
            favorite_teams=json.dumps(favorite_teams or []),
            favorite_sports=json.dumps(favorite_sports or ['football']),
            activated_at=datetime.now(timezone.utc)
        )
        db.session.add(profile)

    db.session.flush()
    return profile


def deactivate_fan_profile(user_id: int) -> bool:
    """
    Deactivate fan profile. Does NOT delete data.
    User can reactivate later and all preferences are restored.
    """
    profile = FanProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        return False
    profile.deactivate()
    # Also reset dashboard context to standard
    _set_dashboard_mode(user_id, 'standard')
    db.session.flush()
    return True


def update_fan_preferences(user_id: int, data: dict) -> FanProfile | None:
    """Update preferences on an existing active FanProfile."""
    profile = FanProfile.query.filter_by(user_id=user_id, is_active=True).first()
    if not profile:
        return None

    if 'favorite_teams' in data:
        profile.favorite_teams = json.dumps(data['favorite_teams'])
    if 'favorite_sports' in data:
        profile.favorite_sports = json.dumps(data['favorite_sports'])
    if 'tournament_notifications' in data:
        profile.tournament_notifications = bool(data['tournament_notifications'])
    if 'match_reminders' in data:
        profile.match_reminders = bool(data['match_reminders'])
    if 'team_news' in data:
        profile.team_news = bool(data['team_news'])
    if 'social_features_enabled' in data:
        profile.social_features_enabled = bool(data['social_features_enabled'])

    profile.updated_at = datetime.now(timezone.utc)
    db.session.flush()
    return profile


def get_dashboard_mode(user) -> str:
    """
    Returns 'standard' or 'tournament'.
    
    Rules:
    - No FanProfile → always 'standard'
    - FanProfile exists but is_active=False → always 'standard'
    - FanProfile active → check UserDashboardContext for current_mode
    - Default for active fan with no context record → 'tournament'
    """
    fan_profile = getattr(user, 'fan_profile', None)

    if not fan_profile or not fan_profile.is_active:
        return 'standard'

    ctx = getattr(user, 'dashboard_context', None)
    if ctx:
        return ctx.current_mode

    return 'tournament'  # Active fan defaults to tournament mode


def _set_dashboard_mode(user_id: int, mode: str):
    """Internal helper to write dashboard context."""
    ctx = UserDashboardContext.query.filter_by(user_id=user_id).first()
    if ctx:
        ctx.current_mode = mode
        ctx.last_updated = datetime.now(timezone.utc)
    else:
        ctx = UserDashboardContext(user_id=user_id, current_mode=mode)
        db.session.add(ctx)

