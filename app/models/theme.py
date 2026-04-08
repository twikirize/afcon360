from app.extensions import db
from datetime import datetime
from app.models.base import ProtectedModel

class GlobalTheme(ProtectedModel):
    __tablename__ = 'global_themes'
    # PK inherited from ProtectedModel/BaseModel as BigInteger
    name = db.Column(db.String(50), default="Default AFCON Green")
    settings = db.Column(db.JSON, nullable=False)  # Map of CSS variables
    is_active = db.Column(db.Boolean, default=True)

class UserThemePreference(db.Model):
    __tablename__ = 'user_theme_preferences'
    # Use BigInteger for FK and PK
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    settings = db.Column(db.JSON, nullable=False)  # darkMode, fontScale, contrastMode etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('theme_preferences', uselist=False))

class EventTheme(db.Model):
    __tablename__ = 'event_themes'
    # Use BigInteger for FK and PK
    event_id = db.Column(db.BigInteger, db.ForeignKey('events.id', ondelete='CASCADE'), primary_key=True)
    settings = db.Column(db.JSON, nullable=False)  # Overrides for specific events
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    event = db.relationship('Event', backref=db.backref('theme', uselist=False))
