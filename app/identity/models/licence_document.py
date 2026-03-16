# app/identity/models/licence_document.py
from sqlalchemy import Column, BigInteger, String, Text, Boolean, DateTime, Date, ForeignKey, Enum, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.extensions import db

# -------------------------------
# Organisation License
# -------------------------------
class OrganisationLicense(db.Model):
    __tablename__ = "organisation_licenses"
    __table_args__ = (
        UniqueConstraint("license_type", "license_number", "country", name="uq_org_license"),
    )

    id = Column(BigInteger, primary_key=True)
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
class OrganisationDocument(db.Model):
    __tablename__ = "organisation_documents"

    id = Column(BigInteger, primary_key=True)
    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), index=True)

    document_type = Column(String(64), index=True)
    storage_key = Column(String(255), nullable=False)
    checksum = Column(String(128), nullable=False)

    version = Column(BigInteger, default=1, nullable=False)
    uploaded_by = Column(BigInteger, ForeignKey("users.id"))

    verification_status = Column(
        Enum("pending", "verified", "rejected", name="doc_verification_status"),
        default="pending",
        nullable=False
    )

    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    verified_at = Column(DateTime)
    expires_at = Column(Date)

    organisation = relationship("Organisation", back_populates="documents")


# -------------------------------
# Organisation Audit Log
# -------------------------------
class OrganisationAuditLog(db.Model):
    __tablename__ = "organisation_audit_logs"

    id = Column(BigInteger, primary_key=True)
    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), index=True)

    field = Column(String(64))
    old_value = Column(Text)
    new_value = Column(Text)

    change_type = Column(
        Enum("create", "update", "delete", "verify", "suspend", name="org_change_type"),
        default="update",
        nullable=False,
        index=True
    )

    source = Column(
        Enum("system", "user", "admin", name="org_change_source"),
        default="user",
        nullable=False,
        index=True
    )

    context = Column(JSON)

    changed_by = Column(BigInteger, ForeignKey("users.id"))
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    organisation = relationship("Organisation", back_populates="audit_logs")
