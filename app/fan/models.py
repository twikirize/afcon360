# app/fan/models.py
# Fan profile and dashboard context models
# All models inherit from BaseModel per project convention

from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel


class FanProfile(BaseModel):
    """
    Optional profile extension. User must explicitly activate in Settings.
    NOT a role. NOT auto-created. User-controlled at all times.
    
    Gate rule: if user.fan_profile is None → show ZERO sports/fan content.
    """
    __tablename__ = 'fan_profiles'

    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        unique=True,
        nullable=False
    )

    # User-controlled activation
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Interests (JSON strings per project convention — no ENUM, no JSONB)
    favorite_teams = db.Column(db.String, default='[]')
    favorite_sports = db.Column(db.String, default='["football"]')

    # Notification preferences
    tournament_notifications = db.Column(db.Boolean, default=True)
    match_reminders = db.Column(db.Boolean, default=True)
    team_news = db.Column(db.Boolean, default=True)

    # Social features (future phase)
    social_features_enabled = db.Column(db.Boolean, default=True)

    # Additional timestamps (BaseModel provides created_at, updated_at)
    activated_at = db.Column(db.DateTime, default=datetime.utcnow)
    deactivated_at = db.Column(db.DateTime, nullable=True)

    # Relationship back to User
    user = db.relationship(
        'User',
        backref=db.backref('fan_profile', uselist=False, lazy='select')
    )

    def activate(self):
        self.is_active = True
        self.activated_at = datetime.utcnow()
        self.deactivated_at = None

    def deactivate(self):
        self.is_active = False
        self.deactivated_at = datetime.utcnow()

    @property
    def favorite_teams_list(self):
        import json
        try:
            return json.loads(self.favorite_teams or '[]')
        except (ValueError, TypeError):
            return []

    @property
    def favorite_sports_list(self):
        import json
        try:
            return json.loads(self.favorite_sports or '[]')
        except (ValueError, TypeError):
            return []

    def __repr__(self):
        return f'<FanProfile user_id={self.user_id} active={self.is_active}>'


class UserDashboardContext(BaseModel):
    """
    Tracks the user's current dashboard mode.
    Separate from FanProfile because this changes frequently (hot data).
    FanProfile is cold data (interests). This is live state.
    
    current_mode values: 'standard' | 'tournament'
    Tournament mode only possible if fan_profile exists and is_active=True.
    """
    __tablename__ = 'user_dashboard_contexts'

    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        unique=True,
        nullable=False
    )

    current_mode = db.Column(db.String(20), default='standard', nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship(
        'User',
        backref=db.backref('dashboard_context', uselist=False, lazy='select')
    )

    def __repr__(self):
        return f'<UserDashboardContext user_id={self.user_id} mode={self.current_mode}>'
