# app/identity/models/individual_document.py

from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship, validates
from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel
from app.utils.enums import IndDocumentType


class IndividualKYCDocument(BaseModel):
    __tablename__ = "individual_documents"
    __table_args__ = (
        CheckConstraint(IndDocumentType.check_constraint(), name="ck_ind_document_type"),
    )

    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Use String + CHECK constraint instead of PostgreSQL ENUM
    document_type = Column(
        String(20),
        nullable=False
    )
    file_path = Column(String(256), nullable=False)
    expires_at = Column(DateTime)

    user = relationship("User", back_populates="documents")

    @validates("document_type")
    def validate_document_type(self, key, value):
        if value and value not in IndDocumentType.values():
            raise ValueError(f"Invalid document_type. Must be one of: {IndDocumentType.values()}")
        return value