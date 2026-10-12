# app/identity/models/compliance_settings.py
from sqlalchemy import Column, BigInteger, String, DateTime, Boolean, ForeignKey, CheckConstraint
from datetime import datetime, timezone
from app.extensions import db
from app.models.base import BaseModel
from app.utils.enums import ComplianceEnforcementLevel


class ComplianceSettings(BaseModel):
    """Compliance settings for enforcement levels on various requirements"""
    __tablename__ = "compliance_settings"

    requirement = Column(String(64), unique=True, nullable=False)
    # Examples: "kyb_verification", "ubo", "license", "wallet_payouts"

    # Use String + CHECK constraint instead of PostgreSQL ENUM
    enforcement_level = Column(
        String(20),
        default=ComplianceEnforcementLevel.OPTIONAL.value,
        nullable=False
    )
    is_enabled = Column(Boolean, default=True, nullable=False)

    updated_by = Column(BigInteger, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint(ComplianceEnforcementLevel.check_constraint(), name="ck_compliance_enforcement_level"),
        {'extend_existing': True}
    )

    def __repr__(self):
        return f"<ComplianceSettings {self.requirement} {self.enforcement_level} enabled={self.is_enabled}>"