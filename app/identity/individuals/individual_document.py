# app/identity/models/individual_document.py

from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import relationship, validates
from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel
from app.utils.enums import IndDocumentType


class IndividualKYCDocument(BaseModel):
    __tablename__ = "individual_documents"

    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Native PostgreSQL ENUM (ind_document_type)
    document_type = Column(
        PgEnum(IndDocumentType, name="ind_document_type", create_type=False, values_callable=lambda c: [e.value for e in c]),
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