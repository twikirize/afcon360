# app/identity/models/licence_document.py
from sqlalchemy import Column, BigInteger, String, Text, Boolean, DateTime, Date, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import relationship, validates
from datetime import datetime, timezone
from app.extensions import db
from app.models.base import BaseModel
from app.utils.enums import (
    DocVerificationStatus,
    OrgChangeType,
    OrgChangeSource,
)

# -------------------------------
# Organisation License
# -------------------------------
class OrganisationLicense(BaseModel):
    __tablename__ = "organisation_licenses"
    __table_args__ = (
        UniqueConstraint("license_type", "license_number", "country", name="uq_org_license"),
    )

    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), index=True)

    license_type = Column(String(64), nullable=False, index=True)
    license_number = Column(String(128), nullable=False, index=True)
    issuing_authority = Column(String(128))
    country = Column(String(2), nullable=False, index=True)

    issued_at = Column(Date)
    expires_at = Column(Date)
    is_active = Column(Boolean, default=True)

    organisation = relationship("Organisation", back_populates="licenses")


# -------------------------------
# Organisation Document
# -------------------------------
class OrganisationDocument(BaseModel):
    __tablename__ = "organisation_documents"

    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), index=True)

    document_type = Column(String(64), index=True)
    storage_key = Column(String(255), nullable=False)
    checksum = Column(String(128), nullable=False)

    version = Column(BigInteger, default=1, nullable=False)
    uploaded_by = Column(BigInteger, ForeignKey("users.id"))

    # Native PostgreSQL ENUM (doc_verification_status)
    verification_status = Column(
        PgEnum(DocVerificationStatus, name="doc_verification_status", create_type=False, values_callable=lambda c: [e.value for e in c]),
        default=DocVerificationStatus.PENDING.value,
        nullable=False
    )

    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    verified_at = Column(DateTime(timezone=True))
    expires_at = Column(Date)

    organisation = relationship("Organisation", back_populates="documents")

    @validates("verification_status")
    def validate_verification_status(self, key, value):
        if value and value not in DocVerificationStatus.values():
            raise ValueError(f"Invalid verification_status. Must be one of: {DocVerificationStatus.values()}")
        return value


# -------------------------------
# Organisation Audit Log
# -------------------------------
class OrganisationAuditLog(BaseModel):
    __tablename__ = "organisation_audit_logs"

    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), index=True)

    field = Column(String(64))
    old_value = Column(Text)
    new_value = Column(Text)

    # Native PostgreSQL ENUM (org_change_type)
    change_type = Column(
        PgEnum(OrgChangeType, name="org_change_type", create_type=False, values_callable=lambda c: [e.value for e in c]),
        default=OrgChangeType.UPDATE.value,
        nullable=False,
        index=True
    )

    source = Column(
        PgEnum(OrgChangeSource, name="org_change_source", create_type=False, values_callable=lambda c: [e.value for e in c]),
        default=OrgChangeSource.USER.value,
        nullable=False,
        index=True
    )

    context = Column(JSON)

    changed_by = Column(BigInteger, ForeignKey("users.id"))
    changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    organisation = relationship("Organisation", back_populates="audit_logs")

    @validates("change_type")
    def validate_change_type(self, key, value):
        if value and value not in OrgChangeType.values():
            raise ValueError(f"Invalid change_type. Must be one of: {OrgChangeType.values()}")
        return value

    @validates("source")
    def validate_source(self, key, value):
        if value and value not in OrgChangeSource.values():
            raise ValueError(f"Invalid source. Must be one of: {OrgChangeSource.values()}")
        return value