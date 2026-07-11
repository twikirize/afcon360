# app/identity/models/individual_document.py

from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel

class IndividualKYCDocument(BaseModel):
    __tablename__ = "individual_documents"

    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    document_type = Column(
        Enum("id_card", "passport", "driver_license", "proof_of_address", name="ind_document_type"),
        nullable=False
    )
    file_path = Column(String(256), nullable=False)
    expires_at = Column(DateTime)

    user = relationship("User", back_populates="documents")
