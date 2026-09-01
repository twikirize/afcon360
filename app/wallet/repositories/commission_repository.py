"""
app/wallet/repositories/commission_repository.py
Repository for AgentCommission model.
"""
from typing import List, Dict, Any, Optional
from decimal import Decimal
from app.extensions import db
from app.wallet.models.commission import AgentCommission
from sqlalchemy import func


class CommissionRepository:
    def __init__(self, session=None):
        self.db = session or db.session

    def create(self, **kwargs) -> AgentCommission:
        commission = AgentCommission(**kwargs)
        self.db.add(commission)
        self.db.flush()
        return commission

    def list_for_agent(self, agent_id: int, limit: int = 50, offset: int = 0) -> List[AgentCommission]:
        q = (
            self.db.query(AgentCommission)
            .filter(AgentCommission.agent_id == agent_id, AgentCommission.is_deleted == False)
            .order_by(AgentCommission.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return q.all()

    def summary_for_agent(self, agent_id: int) -> Dict[str, Any]:
        q = (
            self.db.query(
                func.coalesce(func.sum(AgentCommission.amount), 0).label('total_pending')
            )
            .filter(AgentCommission.agent_id == agent_id, AgentCommission.is_deleted == False, AgentCommission.status == 'pending')
        ).one()

        q2 = (
            self.db.query(
                func.coalesce(func.sum(AgentCommission.amount), 0).label('total_paid')
            )
            .filter(AgentCommission.agent_id == agent_id, AgentCommission.is_deleted == False, AgentCommission.status == 'paid')
        ).one()

        return {
            'agent_id': agent_id,
            'total_pending': str(q.total_pending),
            'total_paid': str(q2.total_paid)
        }

    def settle_for_payout(self, agent_id: int, currency: str, amount: Decimal) -> None:
        """Mark unpaid commissions for an agent/currency as paid, settling up to
        ``amount`` total (oldest first). Idempotent: rows already paid are skipped."""
        rows = (
            self.db.query(AgentCommission)
            .filter(
                AgentCommission.agent_id == agent_id,
                AgentCommission.currency == currency,
                AgentCommission.status != 'paid',
                AgentCommission.is_deleted == False,
            )
            .order_by(AgentCommission.created_at.asc())
            .all()
        )
        remaining = Decimal(amount)
        for commission in rows:
            if remaining <= Decimal('0'):
                break
            commission.status = 'paid'
            commission.paid_at = func.now()
            self.db.add(commission)
            remaining -= Decimal(str(commission.amount))
        self.db.flush()

    def get_by_ref(self, commission_ref: str):
        return self.db.query(AgentCommission).filter(AgentCommission.commission_ref == commission_ref, AgentCommission.is_deleted == False).first()

    def mark_paid(self, commission_ref: str, paid_by: Optional[int] = None):
        commission = self.get_by_ref(commission_ref)
        if not commission:
            return None
        commission.status = 'paid'
        commission.paid_by = paid_by
        commission.paid_at = func.now()
        self.db.add(commission)
        self.db.flush()
        return commission

