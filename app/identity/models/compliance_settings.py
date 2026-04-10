# app/identity/models/compliance_settings.py

from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, Enum, ForeignKey
from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel

class ComplianceSettings(BaseModel):
    __tablename__ = "compliance_settings"

    requirement = Column(String(64), unique=True, nullable=False)
    # Examples: "kyb_verification", "ubo", "license", "wallet_payouts"

    enforcement_level = Column(
        Enum("optional", "conditional", "mandatory", name="compliance_enforcement_level"),
        default="optional",
        nullable=False
    )
    is_enabled = Column(Boolean, default=True, nullable=False)

    updated_by = Column(BigInteger, ForeignKey("users.id"))

    def __repr__(self):
        return f"<ComplianceSettings {self.requirement} {self.enforcement_level} enabled={self.is_enabled}>"
