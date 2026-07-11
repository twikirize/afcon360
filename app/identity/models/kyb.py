# app/identity/models/kyb.py
from sqlalchemy import Column, BigInteger, String, Text, DateTime, Enum, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel


# -------------------------------
# Organisation Verification
# -------------------------------
class OrganisationVerification(BaseModel):
    __tablename__ = "organisation_verifications"

    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))

    status = Column(
        Enum("pending", "verified", "rejected", "expired", "suspended", name="org_verification_status"),
        default="pending", nullable=False, index=True
    )
    scope = Column(JSON, default=dict)
    provider_id = Column(String(128))
    notes = Column(Text)

    decided_at = Column(DateTime)
    expires_at = Column(DateTime)

    organisation = relationship(
        "Organisation",
        back_populates="verifications",
        foreign_keys=[organisation_id]
    )
    reviewer = relationship(
        "User",
        foreign_keys=[reviewer_id]
    )


# -------------------------------
# Organisation KYB Check
# -------------------------------
class OrganisationKYBCheck(BaseModel):
    __tablename__ = "organisation_kyb_checks"

    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)

    check_type = Column(Enum("identity", "tax", "license", "ubo", "sanctions", name="org_kyb_check_type"),
                        nullable=False)
    status = Column(Enum("pending", "passed", "failed", "manual_review", name="org_kyb_check_status"),
                    default="pending")
    provider_id = Column(String(128))
    evidence = Column(JSON)
    notes = Column(Text)

    organisation = relationship(
        "Organisation",
        back_populates="kyb_checks",
        foreign_keys=[organisation_id]
    )


# -------------------------------
# Organisation UBO
# -------------------------------
class OrganisationUBO(BaseModel):
    __tablename__ = "organisation_ubos"

    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    verified_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))

    ubo_type = Column(Enum("individual", "corporate", name="ubo_type"), default="individual")
    ownership_percentage = Column(BigInteger)
    effective_from = Column(DateTime)
    effective_to = Column(DateTime)

    verified_at = Column(DateTime)

    organisation = relationship(
        "Organisation",
        back_populates="ubos",
        foreign_keys=[organisation_id]
    )
    user = relationship(
        "User",
        foreign_keys=[user_id]
    )
    verifier = relationship(
        "User",
        foreign_keys=[verified_by]
    )


# -------------------------------
# Organisation KYB Document
# -------------------------------
class OrganisationKYBDocument(BaseModel):
    __tablename__ = "organisation_kyb_documents"

    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)

    document_type = Column(String(64), nullable=False)
    storage_key = Column(String(255), nullable=False)
    checksum = Column(String(128), nullable=False)
    verification_status = Column(
        Enum("pending", "verified", "rejected", name="kyb_doc_status"),
        default="pending"
    )

    organisation = relationship(
        "Organisation",
        back_populates="kyb_documents",
        foreign_keys=[organisation_id]
    )
