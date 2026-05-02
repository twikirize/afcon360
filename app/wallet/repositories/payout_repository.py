from typing import List, Dict, Any
from app.extensions import db
from app.wallet.models.payout import PayoutRequest


class PayoutRepository:
    def __init__(self, session=None):
        self.db = session or db.session

    def create(self, **kwargs) -> PayoutRequest:
        pr = PayoutRequest(**kwargs)
        self.db.add(pr)
        self.db.flush()
        return pr

    def list_for_agent(self, agent_id: int, limit: int = 50, offset: int = 0) -> List[PayoutRequest]:
        return (
            self.db.query(PayoutRequest)
            .filter(PayoutRequest.agent_id == agent_id, PayoutRequest.is_deleted == False)
            .order_by(PayoutRequest.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def get(self, request_ref: str) -> PayoutRequest:
        return self.db.query(PayoutRequest).filter(PayoutRequest.request_ref == request_ref, PayoutRequest.is_deleted == False).first()

