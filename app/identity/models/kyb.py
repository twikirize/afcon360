# app/identity/models/kyb.py
from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import relationship, validates
from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel
from app.utils.enums import (
    OrgVerificationStatus,
    OrgKybCheckType,
    OrgKybCheckStatus,
    UboType,
    KybDocStatus,
)


# -------------------------------
# Organisation Verification
# -------------------------------
class OrganisationVerification(BaseModel):
    __tablename__ = "organisation_verifications"

    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))

    # Native PostgreSQL ENUM (org_verification_status)
    status = Column(
        PgEnum(OrgVerificationStatus, name="org_verification_status", create_type=False, values_callable=lambda c: [e.value for e in c]),
        default=OrgVerificationStatus.PENDING.value,
        nullable=False,
        index=True
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

    # Native PostgreSQL ENUM (org_kyb_check_type)
    check_type = Column(
        PgEnum(OrgKybCheckType, name="org_kyb_check_type", create_type=False, values_callable=lambda c: [e.value for e in c]),
        nullable=False
    )
    status = Column(
        PgEnum(OrgKybCheckStatus, name="org_kyb_check_status", create_type=False, values_callable=lambda c: [e.value for e in c]),
        default=OrgKybCheckStatus.PENDING.value
    )
    provider_id = Column(String(128))
    evidence = Column(JSON)
    notes = Column(Text)

    organisation = relationship(
        "Organisation",
        back_populates="kyb_checks",
        foreign_keys=[organisation_id]
    )

    @validates("check_type")
    def validate_check_type(self, key, value):
        if value and value not in OrgKybCheckType.values():
            raise ValueError(f"Invalid check_type. Must be one of: {OrgKybCheckType.values()}")
        return value

    @validates("status")
    def validate_status(self, key, value):
        if value and value not in OrgKybCheckStatus.values():
            raise ValueError(f"Invalid status. Must be one of: {OrgKybCheckStatus.values()}")
        return value


# -------------------------------
# Organisation UBO
# -------------------------------
class OrganisationUBO(BaseModel):
    __tablename__ = "organisation_ubos"

    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    verified_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))

    # Native PostgreSQL ENUM (ubo_type)
    ubo_type = Column(
        PgEnum(UboType, name="ubo_type", create_type=False, values_callable=lambda c: [e.value for e in c]),
        default=UboType.INDIVIDUAL.value
    )
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

    @validates("ubo_type")
    def validate_ubo_type(self, key, value):
        if value and value not in UboType.values():
            raise ValueError(f"Invalid ubo_type. Must be one of: {UboType.values()}")
        return value


# -------------------------------
# Organisation KYB Document
# -------------------------------
class OrganisationKYBDocument(BaseModel):
    __tablename__ = "organisation_kyb_documents"

    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)

    document_type = Column(String(64), nullable=False)
    storage_key = Column(String(255), nullable=False)
    checksum = Column(String(128), nullable=False)
    # Native PostgreSQL ENUM (kyb_doc_status)
    verification_status = Column(
        PgEnum(KybDocStatus, name="kyb_doc_status", create_type=False, values_callable=lambda c: [e.value for e in c]),
        default=KybDocStatus.PENDING.value
    )

    organisation = relationship(
        "Organisation",
        back_populates="kyb_documents",
        foreign_keys=[organisation_id]
    )

    @validates("verification_status")
    def validate_verification_status(self, key, value):
        if value and value not in KybDocStatus.values():
            raise ValueError(f"Invalid verification_status. Must be one of: {KybDocStatus.values()}")
        return value