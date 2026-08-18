# app/accommodation/models/guest_registration.py
"""
Guest Registration model - tracks per-booking guest registration status.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Text,
    ForeignKey, Index, UniqueConstraint, CheckConstraint, Integer, Date
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class GuestRegistration(BaseModel):
    """
    Per-booking guest registration record.
    Tracks identity documents and registration status for each guest.
    """
    __tablename__ = "accommodation_guest_registrations"
    __table_args__ = (
        UniqueConstraint("booking_id", "guest_user_id", name="uq_booking_guest"),
        Index("idx_guest_reg_booking", "booking_id"),
        Index("idx_guest_reg_user", "guest_user_id"),
        Index("idx_guest_reg_status", "status"),
        Index("idx_guest_reg_active", "booking_id", "is_active"),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'skipped')",
            name="ck_guest_reg_status_valid"
        ),
    )

    # -------------------------------
    # Relationships
    # -------------------------------
    booking_id = Column(BigInteger, ForeignKey("accommodation_bookings.id", ondelete="CASCADE"), nullable=False)
    booking = relationship("AccommodationBooking", back_populates="guest_registrations")

    guest_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    guest_user = relationship("User", foreign_keys=[guest_user_id])

    # -------------------------------
    # Guest Details
    # -------------------------------
    guest_name = Column(String(255), nullable=False)
    guest_email = Column(String(255), nullable=True)
    guest_phone = Column(String(50), nullable=True)

    # Relationship to primary booker
    relationship_type = Column(String(30), nullable=False, default="adult")  # primary, adult, child, infant
    age = Column(Integer, nullable=True)

    # Host-configurable fields (D-024)
    date_of_birth = Column(Date, nullable=True)
    nationality = Column(String(100), nullable=True)

    # -------------------------------
    # Identity Documents
    # -------------------------------
    id_document_type = Column(String(30), nullable=True)  # passport, national_id, drivers_license, birth_certificate
    id_document_number = Column(String(100), nullable=True)
    id_document_url = Column(String(500), nullable=True)  # Storage key or URL
    id_document_expiry = Column(Date, nullable=True)

    # -------------------------------
    # Registration Status
    # -------------------------------
    status = Column(String(30), nullable=False, default="pending")
    is_verified = Column(Boolean, default=False, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # -------------------------------
    # Host Override
    # -------------------------------
    host_override = Column(Boolean, default=False, nullable=False)
    host_override_reason = Column(Text, nullable=True)
    host_override_at = Column(DateTime(timezone=True), nullable=True)
    host_override_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # -------------------------------
    # Metadata
    # -------------------------------
    notes = Column(Text, nullable=True)
    registration_source = Column(String(30), nullable=True)  # self, host, admin

    # Slot lifecycle and reassignment audit trail.
    is_active = Column(Boolean, default=True, server_default="true", nullable=False)
    is_placeholder = Column(Boolean, default=False, server_default="false", nullable=False)
    replaces_registration_id = Column(
        BigInteger,
        ForeignKey(
            "accommodation_guest_registrations.id",
            ondelete="SET NULL",
            name="fk_guest_reg_replaces_registration",
        ),
        nullable=True,
    )
    removed_at = Column(DateTime(timezone=True), nullable=True)
    removed_by_user_id = Column(
        BigInteger,
        ForeignKey("users.id", name="fk_guest_reg_removed_by_user"),
        nullable=True,
    )
    removed_reason = Column(Text, nullable=True)
    import_batch_id = Column(String(64), nullable=True, index=True)

    # -------------------------------
    # Timestamps
    # -------------------------------
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<GuestRegistration {self.booking_id}:{self.guest_name} ({self.status})>"

    @property
    def is_primary(self) -> bool:
        return self.relationship_type == "primary"

    def mark_completed(self, verified_by_user_id: int = None):
        self.status = "completed"
        self.is_verified = True
        self.verified_at = datetime.now(timezone.utc)
        if verified_by_user_id:
            self.verified_by = verified_by_user_id

    def mark_skipped(self, reason: str = None, overridden_by_user_id: int = None):
        self.status = "skipped"
        self.host_override = True
        self.host_override_reason = reason
        self.host_override_at = datetime.now(timezone.utc)
        if overridden_by_user_id:
            self.host_override_by = overridden_by_user_id

    def remove(self, removed_by_user_id: int, reason: str):
        """Retire a slot without deleting its identity or document history."""
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("A removal reason is required")
        self.is_active = False
        self.removed_at = datetime.now(timezone.utc)
        self.removed_by_user_id = removed_by_user_id
        self.removed_reason = reason
