"""
app/wallet/services/commission_service.py

Minimal CommissionService implementation to satisfy imports from
`app.wallet.api.wallet_api`. This provides two methods used by the
API: `get_commission_summary` and `get_agent_commissions`.

This is intentionally lightweight: it returns sensible empty/default
structures so the API can start even if the full commission engine is
not present. Replace with full business logic as needed.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4
from flask import current_app

from app.extensions import db
from app.wallet.repositories.commission_repository import CommissionRepository
from app.wallet.repositories.payout_repository import PayoutRepository


class CommissionService:
    """Robust commission service.

    Responsibilities:
    - Calculate commission amounts based on configurable rules.
    - Persist AgentCommission records (pending) so agents can request payouts.
    - Provide list/summary APIs for the wallet API layer.

    Commission rules are read from `current_app.config['COMMISSION_RULES']`.
    Example:
        COMMISSION_RULES = {
            'transfer': {'rate': Decimal('0.01'), 'agent_share': Decimal('0.7')},
            'withdraw': {'rate': Decimal('0.02'), 'agent_share': Decimal('0.5')},
        }
    """

    def __init__(self, db_session=None):
        self.db = db_session or db.session
        self.repo = CommissionRepository(self.db)

    def _get_rule(self, source_type: str) -> Dict[str, Decimal]:
        rules = current_app.config.get('COMMISSION_RULES', {})
        r = rules.get(source_type, {})
        return {
            'rate': Decimal(str(r.get('rate', '0'))),
            'agent_share': Decimal(str(r.get('agent_share', '0')))
        }

    def calculate_commission(self, amount: Decimal, source_type: str, platform_fee: Optional[Decimal] = None) -> Decimal:
        """Calculate commission amount for a given source and amount.

        If platform_fee is supplied, it is used as the commission base.
        """
        if platform_fee is not None:
            base = platform_fee
        else:
            rule = self._get_rule(source_type)
            base = amount * rule['rate']

        # Quantize to 6 decimal places (matches DB Numeric(18,6))
        return Decimal(base).quantize(Decimal('0.000001'))

    def record_commission(
        self,
        agent_id: int,
        amount: Decimal,
        currency: str,
        source_type: str,
        source_id: str,
        recipient_id: Optional[int] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create an AgentCommission record inside an existing DB transaction.

        This does NOT perform ledger postings. Payouts will create ledger
        entries when commissions are actually paid to agents.
        """
        commission_ref = f"cm_{uuid4().hex[:16]}"

        commission = self.repo.create(
            commission_ref=commission_ref,
            agent_id=agent_id,
            amount=amount,
            currency=currency,
            source_type=source_type,
            source_id=source_id,
            recipient_id=recipient_id,
            extra_data=extra_data or {},
            status='pending'
        )

        # flush/commit handled by caller transaction
        return {
            'commission_ref': commission_ref,
            'agent_id': agent_id,
            'amount': str(amount),
            'currency': currency,
            'status': 'pending'
        }

    def get_commission_summary(self, agent_id: int) -> Dict[str, Any]:
        return self.repo.summary_for_agent(agent_id)

    def get_agent_commissions(
        self,
        agent_id: int,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        rows = self.repo.list_for_agent(agent_id, limit=limit, offset=offset)
        return [
            {
                'id': r.id,
                'commission_ref': r.commission_ref,
                'agent_id': r.agent_id,
                'amount': str(r.amount),
                'currency': r.currency,
                'status': r.status,
                'source_type': r.source_type,
                'source_id': r.source_id,
                'recipient_id': r.recipient_id,
                'created_at': r.created_at.isoformat(),
                'extra_data': r.extra_data or {}
            }
            for r in rows
        ]


