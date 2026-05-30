from datetime import datetime
from sqlalchemy import Column, String, Numeric, DateTime, Index, BigInteger, Text
from app.models.base import BaseModel
from app.extensions import db


class PayoutRequest(BaseModel):
    __tablename__ = 'payout_requests'

    request_ref = Column(String(64), unique=True, nullable=False)
    agent_id = Column(BigInteger, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    amount = Column(Numeric(18, 6), nullable=False)
    currency = Column(String(10), nullable=False)
    payment_method = Column(String(30), nullable=False)
    payment_details = Column(db.JSON, nullable=False)
    status = Column(String(20), nullable=False, default='pending', index=True)
    approved_by = Column(BigInteger, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    paid_by = Column(BigInteger, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    paid_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index('ix_payout_requests_agent', 'agent_id'),
        Index('ix_payout_requests_status', 'status'),
    )

    def __repr__(self):
        return f"<PayoutRequest {self.request_ref} agent={self.agent_id} amount={self.amount}>"

