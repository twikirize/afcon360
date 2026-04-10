# app/identity/models/organisation_controller.py
from sqlalchemy import Column, BigInteger, Date, DateTime, Enum, ForeignKey,String
from sqlalchemy.orm import relationship
from datetime import datetime
from app.extensions import db

# --------------------------------------
# Organisation Controller
# --------------------------------------
class OrganisationController(db.Model):
    __tablename__ = "organisation_controllers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    added_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))

    role = Column(String(64))
    appointed_at = Column(DateTime, default=datetime.utcnow)

    organisation = relationship(
        "Organisation",
        back_populates="controllers",
        foreign_keys=[organisation_id]
    )

    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="controllers"
    )

    added_by_user = relationship(
        "User",
        foreign_keys=[added_by]
    )
