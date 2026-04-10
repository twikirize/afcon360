from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel

class FanProfile(BaseModel):
    __tablename__ = "fan_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, unique=True, index=True)

    display_name = db.Column(db.String(128), nullable=False)
    nationality = db.Column(db.String(64), nullable=True)
    favorite_team = db.Column(db.String(128), nullable=True)
    avatar_url = db.Column(db.String(256), nullable=True)
    bio = db.Column(db.String(512), nullable=True)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
