#app/fan/models

from datetime import datetime
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel

class FanProfile(BaseModel):
    __tablename__ = "fan_profiles"

    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, unique=True, index=True)

    display_name = db.Column(db.String(128), nullable=False)
    nationality = db.Column(db.String(64), nullable=True)
    favorite_team = db.Column(db.String(128), nullable=True)
    avatar_url = db.Column(db.String(256), nullable=True)
    bio = db.Column(db.String(512), nullable=True)

    # KYC verification relationship
    verification_id = db.Column(db.BigInteger, db.ForeignKey("individual_verifications.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    verification = relationship(
        "IndividualVerification",
        foreign_keys=[verification_id],
        post_update=True
    )

    @property
    def kyc_status(self):
        """Get the KYC status from linked verification"""
        if self.verification:
            return self.verification.status
        return None

    @property
    def is_kyc_verified(self):
        """Check if KYC is verified"""
        return self.kyc_status == "verified"

    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        # Add KYC status to the dictionary
        data['kyc_status'] = self.kyc_status
        data['is_kyc_verified'] = self.is_kyc_verified
        # Remove verification_id if it's None to keep the API clean
        if data.get('verification_id') is None:
            data.pop('verification_id', None)
        return data
