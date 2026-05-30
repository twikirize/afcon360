"""
app/wallet/models/commission.py

Agent commission model.
"""
from datetime import datetime
from sqlalchemy import Column, String, Numeric, DateTime, Index, BigInteger
from app.models.base import BaseModel
from app.extensions import db


class AgentCommission(BaseModel):
    __tablename__ = 'agent_commissions'

    commission_ref = Column(String(64), unique=True, nullable=False)
    agent_id = Column(BigInteger, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    amount = Column(Numeric(18, 6), nullable=False)
    currency = Column(String(10), nullable=False)
    source_type = Column(String(30), nullable=False)
    source_id = Column(String(64), nullable=False)
    recipient_id = Column(BigInteger, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    status = Column(String(20), nullable=False, default='pending', index=True)
    paid_at = Column(DateTime, nullable=True)
    paid_by = Column(BigInteger, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    extra_data = Column(db.JSON, nullable=True, default=dict)

    __table_args__ = (
        Index('ix_agent_commissions_agent', 'agent_id'),
        Index('ix_agent_commissions_status', 'status'),
        Index('ix_agent_commissions_source', 'source_type', 'source_id'),
    )

    def __repr__(self):
        return f"<AgentCommission {self.commission_ref} agent={self.agent_id} amount={self.amount}>"

