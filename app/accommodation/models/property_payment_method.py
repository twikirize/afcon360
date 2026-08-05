# app/accommodation/models/property_payment_method.py
"""
Property Payment Method Model - Maps enabled payment methods per property
"""

from sqlalchemy import (
    Column, BigInteger, Boolean, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class PropertyPaymentMethod(BaseModel):
    """
    Links a property to an enabled wallet payment method.
    Controls which payment methods a property accepts.
    """
    __tablename__ = "accommodation_property_payment_methods"
    __table_args__ = (
        Index("idx_payment_method_property", "property_id"),
        Index("idx_payment_method_wallet", "wallet_method_id"),
        UniqueConstraint(
            "property_id", "wallet_method_id",
            name="uq_property_payment_method"
        ),
    )

    property_id = Column(
        BigInteger,
        ForeignKey("accommodation_properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    property = relationship("Property", back_populates="payment_methods")

    wallet_method_id = Column(BigInteger, nullable=False, )
    enabled = Column(Boolean, default=True)

    def __repr__(self):
        return (
            f"<PropertyPaymentMethod property={self.property_id} "
            f"method={self.wallet_method_id} enabled={self.enabled}>"
        )
