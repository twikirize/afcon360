from sqlalchemy import Column, BigInteger, String, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class PropertyModerationHistory(BaseModel):
    __tablename__ = 'accommodation_property_moderation_history'
    
    property_id = Column(BigInteger, ForeignKey('accommodation_properties.id'), nullable=False)
    action = Column(String(50), nullable=False)  # submitted, approved, rejected, changes_requested, suspended, reinstated
    previous_status = Column(String(50))
    new_status = Column(String(50))
    reason = Column(Text)
    moderated_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    notes = Column(Text)
    
    property = relationship('Property', foreign_keys=[property_id])
    moderator = relationship('User', foreign_keys=[moderated_by])
