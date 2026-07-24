from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, Boolean, DateTime, Numeric, Text
)
from app.extensions import db
from app.models.base import BaseModel


class PlatformBookingPolicyOverride(BaseModel):
    """
    Platform-wide overrides for booking policies.
    Admin can enforce minimum deposit, maximum pay-on-arrival, etc.
    """
    __tablename__ = "accommodation_platform_policy_overrides"

    id = Column(Integer, primary_key=True)

    # Minimum deposit percentage (0-100)
    minimum_deposit_percentage = Column(Numeric(5, 2), default=0)

    # Maximum pay-on-arrival period in days (0 = disabled)
    maximum_pay_on_arrival_days = Column(Integer, default=0)

    # VIP requirements
    require_vip_verification = Column(Boolean, default=False)

    # AFCON event restrictions
    afcon_restrictions_active = Column(Boolean, default=False)
    afcon_pay_on_arrival_disabled = Column(Boolean, default=False)

    # Audit
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<PlatformBookingPolicyOverride id={self.id}>"
