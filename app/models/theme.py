from app.extensions import db
from datetime import datetime
from app.models.base import ProtectedModel, BaseModel

class GlobalTheme(ProtectedModel):
    __tablename__ = 'global_themes'
    # PK inherited from ProtectedModel/BaseModel as BigInteger
    name = db.Column(db.String(50), default="Default AFCON Green")
    settings = db.Column(db.JSON, nullable=False)  # Map of CSS variables
    is_active = db.Column(db.Boolean, default=True)

class UserThemePreference(BaseModel):
    __tablename__ = 'user_theme_preferences'

    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    settings = db.Column(db.JSON, nullable=False)  # darkMode, fontScale, contrastMode etc.

    user = db.relationship('User', backref=db.backref('theme_preferences', uselist=False))

class EventTheme(BaseModel):
    __tablename__ = 'event_themes'

    event_id = db.Column(db.BigInteger, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    settings = db.Column(db.JSON, nullable=False)  # Overrides for specific events

    event = db.relationship('Event', backref=db.backref('theme', uselist=False))
