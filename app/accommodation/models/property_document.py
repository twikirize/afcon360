# app/accommodation/models/property_document.py
"""
Property Document models - Documents uploaded for property verification.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime,
    ForeignKey, Text, Enum, Index
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel
import enum


class PropertyDocumentType(enum.Enum):
    ID_DOCUMENT = "id_document"
    BUSINESS_LICENSE = "business_license"
    TAX_CERTIFICATE = "tax_certificate"
    PROPERTY_DEED = "property_deed"
    INSURANCE_CERTIFICATE = "insurance_certificate"
    OTHER = "other"


class PropertyDocumentStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PropertyDocument(BaseModel):
    """
    Document uploaded for property verification.
    Can be attached to either a Property or a HostProfile.
    """
    __tablename__ = "accommodation_property_documents"
    __table_args__ = (
        Index("idx_property_document_property", "property_id"),
        Index("idx_property_document_host", "host_user_id"),
        Index("idx_property_document_status", "status"),
    )

    # ── Attachments ──
    property_id = Column(
        BigInteger,
        ForeignKey("accommodation_properties.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    property = relationship("Property", backref="documents")

    host_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    host_user = relationship("User", foreign_keys=[host_user_id], backref="property_documents")

    # ── Document info ──
    document_type = Column(
        Enum(PropertyDocumentType),
        nullable=False,
        index=True
    )
    file_url = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # ── Verification ──
    status = Column(
        Enum(PropertyDocumentStatus),
        default=PropertyDocumentStatus.PENDING,
        nullable=False,
        index=True
    )
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    expiry_date = Column(DateTime(timezone=True), nullable=True)

    # ── Metadata ──
    extra_data = Column(db.JSON, default=dict)

    def __repr__(self):
        return f"<PropertyDocument {self.document_type.value} status={self.status.value}>"
