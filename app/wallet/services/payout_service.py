"""
app/wallet/services/payout_service.py

Lightweight PayoutService stub to satisfy imports from the wallet API.
Provides methods used by the API: create_request, list_requests and
get_agent_payout_summary. Replace with full implementation backed by
repositories/DB when available.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4
from flask import current_app

from app.extensions import db
from app.wallet.repositories.payout_repository import PayoutRepository


class PayoutService:
    def __init__(self, db_session=None):
        self.db = db_session or db.session
        self.repo = PayoutRepository(self.db)

    def create_request(
        self,
        agent_id: int,
        amount: Decimal,
        currency: str,
        payment_method: str,
        payment_details: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a payout request persisted in DB.

        Returns a dict describing the created payout request. Caller should
        wrap in a DB transaction if needed.
        """
        request_ref = f"pr_{uuid4().hex[:16]}"
        pr = self.repo.create(
            request_ref=request_ref,
            agent_id=agent_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            payment_details=payment_details,
            status='pending'
        )
        return {
            'request_ref': request_ref,
            'agent_id': agent_id,
            'amount': str(amount),
            'currency': currency,
            'payment_method': payment_method,
            'status': 'pending'
        }

    def list_requests(
        self,
        agent_id: int,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        rows = self.repo.list_for_agent(agent_id, limit=limit, offset=offset)
        return [
            {
                'request_ref': r.request_ref,
                'amount': str(r.amount),
                'currency': r.currency,
                'status': r.status,
                'created_at': r.created_at.isoformat()
            }
            for r in rows
        ]

    def get_agent_payout_summary(self, agent_id: int) -> Dict[str, Any]:
        # Simple aggregation - can be optimized with SQL
        rows = self.repo.list_for_agent(agent_id, limit=1000)
        total_pending = sum([float(r.amount) for r in rows if r.status == 'pending'])
        total_paid = sum([float(r.amount) for r in rows if r.status == 'paid'])
        return {
            'agent_id': agent_id,
            'total_pending': str(total_pending),
            'total_paid': str(total_paid)
        }

