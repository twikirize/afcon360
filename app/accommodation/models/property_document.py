# app/accommodation/models/property_document.py
"""
Property Document models - Documents uploaded for property verification.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime,
    ForeignKey, Text, Index
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import relationship, validates
from app.extensions import db
from app.models.base import BaseModel
from app.utils.enums import (
    PropertyDocumentType,
    PropertyDocumentStatus,
)


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
    # Native PostgreSQL ENUM (propertydocumenttype)
    document_type = Column(
        PgEnum(PropertyDocumentType, name="propertydocumenttype", create_type=False),
        nullable=False,
        index=True
    )
    file_url = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # ── Verification ──
    # Native PostgreSQL ENUM (propertydocumentstatus)
    status = Column(
        PgEnum(PropertyDocumentStatus, name="propertydocumentstatus", create_type=False),
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
        return f"<PropertyDocument {self.document_type} status={self.status}>"

    @validates("document_type")
    def validate_document_type(self, key, value):
        if value and value not in PropertyDocumentType.values():
            raise ValueError(f"Invalid document_type. Must be one of: {PropertyDocumentType.values()}")
        return value

    @validates("status")
    def validate_status(self, key, value):
        if value and value not in PropertyDocumentStatus.values():
            raise ValueError(f"Invalid status. Must be one of: {PropertyDocumentStatus.values()}")
        return value