# app/identity/models/individual_document.py

from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from app.extensions import db

class IndividualKYCDocument(db.Model):
    __tablename__ = "individual_documents"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    document_type = Column(
        Enum("id_card", "passport", "driver_license", "proof_of_address", name="ind_document_type"),
        nullable=False
    )
    file_path = Column(String(256), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)

    user = relationship("User", back_populates="documents")
