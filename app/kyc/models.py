# app/kyc/user.py
from app.extensions import db
from app.models.base import TimestampMixin

class KycRecord(TimestampMixin, db.Model):
    __tablename__ = "kyc_records"

    id = db.Column(db.Integer, primary_key=True)
    #user_id = db.Column(db.String(36), db.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # kyc content
    id_type = db.Column(db.String(50), nullable=False)  # passport, national_id, dl
    id_number = db.Column(db.String(128), nullable=False)
    document_url = db.Column(db.String(2048), nullable=True)  # store in secure bucket
    selfie_url = db.Column(db.String(2048), nullable=True)
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    state = db.Column(db.String(120), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(2), nullable=True)

    # verification workflow
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)  # pending/approved/rejected
    provider = db.Column(db.String(50), nullable=True)  # external KYC provider tag
    checked_by = db.Column(db.String(80), nullable=True)  # admin username or service id
    verified_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(1024), nullable=True)

    user = db.relationship("User", back_populates="kyc_records")

    __table_args__ = (
        db.Index("ix_kyc_user_status", "user_id", "status"),
    )