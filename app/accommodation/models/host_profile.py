# app/accommodation/models/host_profile.py
"""
Host Profile models - Individual and organisation host profiles.
Tracks host-specific data: KYC tier, payout settings, performance, etc.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Numeric,
    ForeignKey, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class HostProfile(BaseModel):
    """
    Individual host profile.
    Extends the base User with accommodation-specific host data.
    """
    __tablename__ = "accommodation_host_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_host_profile_user"),
        Index("idx_host_profile_user", "user_id"),
        Index("idx_host_profile_active", "is_active_host"),
    )

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user = relationship("User", foreign_keys=[user_id], backref="host_profile")

    # ── Host status ──
    is_active_host = Column(Boolean, default=True, nullable=False)
    is_suspended = Column(Boolean, default=False, nullable=False)
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspended_reason = Column(String(500), nullable=True)
    suspended_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # ── Onboarding ──
    onboarding_completed = Column(Boolean, default=False, nullable=False)
    onboarding_step = Column(String(50), default="register", nullable=False)
    # Steps: register → listing → rooms → go_live

    # ── Payout settings ──
    default_payout_method = Column(String(50), default="wallet", nullable=False)
    # wallet, bank_transfer, mobile_money

    # ── Commission / fees ──
    commission_override_pct = Column(Numeric(5, 2), nullable=True)
    # NULL = use platform default. Host-specific negotiated rate.

    # ── Tax / compliance ──
    tax_id = Column(String(128), nullable=True, index=True)
    tax_country = Column(String(2), nullable=True)
    vat_number = Column(String(64), nullable=True)

    # ── Stats (denormalized for performance, refreshed by Celery) ──
    total_listings = Column(BigInteger, default=0, nullable=False)
    active_listings = Column(BigInteger, default=0, nullable=False)
    total_bookings = Column(BigInteger, default=0, nullable=False)
    total_reviews = Column(BigInteger, default=0, nullable=False)
    avg_rating = Column(Numeric(3, 2), nullable=True)
    total_earnings = Column(Numeric(12, 2), default=0, nullable=False)
    pending_payout = Column(Numeric(12, 2), default=0, nullable=False)

    # ── Metadata ──
    extra_data = Column(db.JSON, default=dict)

    def __repr__(self):
        return f"<HostProfile user={self.user_id} active={self.is_active_host}>"


class HostOrganisationProfile(BaseModel):
    """
    Organisation host profile.
    Tracks organisation-level host settings, payout accounts, and stats.
    """
    __tablename__ = "accommodation_host_org_profiles"
    __table_args__ = (
        UniqueConstraint("org_id", name="uq_host_org_profile_org"),
        Index("idx_host_org_profile_org", "org_id"),
        Index("idx_host_org_profile_active", "is_active_host"),
    )

    org_id = Column(
        BigInteger,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    org = relationship("Organisation", foreign_keys=[org_id], backref="host_profile")

    # ── Host status ──
    is_active_host = Column(Boolean, default=True, nullable=False)
    is_suspended = Column(Boolean, default=False, nullable=False)
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspended_reason = Column(String(500), nullable=True)
    suspended_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # ── Onboarding ──
    onboarding_completed = Column(Boolean, default=False, nullable=False)
    onboarding_step = Column(String(50), default="register", nullable=False)

    # ── Payout settings ──
    default_payout_method = Column(String(50), default="bank_transfer", nullable=False)
    payout_account_details = Column(db.JSON, default=dict)
    # { "bank_name": "...", "account_number": "...", "account_name": "...", "swift_code": "..." }

    # ── Commission / fees ──
    commission_override_pct = Column(Numeric(5, 2), nullable=True)

    # ── Tax / compliance ──
    tax_id = Column(String(128), nullable=True, index=True)
    tax_country = Column(String(2), nullable=True)
    vat_number = Column(String(64), nullable=True)
    business_registration_no = Column(String(128), nullable=True)

    # ── Stats ──
    total_listings = Column(BigInteger, default=0, nullable=False)
    active_listings = Column(BigInteger, default=0, nullable=False)
    total_bookings = Column(BigInteger, default=0, nullable=False)
    total_reviews = Column(BigInteger, default=0, nullable=False)
    avg_rating = Column(Numeric(3, 2), nullable=True)
    total_earnings = Column(Numeric(12, 2), default=0, nullable=False)
    pending_payout = Column(Numeric(12, 2), default=0, nullable=False)

    # ── Metadata ──
    extra_data = Column(db.JSON, default=dict)

    def __repr__(self):
        return f"<HostOrganisationProfile org={self.org_id} active={self.is_active_host}>"
