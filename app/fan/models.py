from datetime import datetime
from app.extensions import db

class FanProfile(db.Model):
    __tablename__ = "fan_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, unique=True, index=True)

    display_name = db.Column(db.String(128), nullable=False)
    nationality = db.Column(db.String(64), nullable=True)
    favorite_team = db.Column(db.String(128), nullable=True)
    avatar_url = db.Column(db.String(256), nullable=True)
    bio = db.Column(db.String(512), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}