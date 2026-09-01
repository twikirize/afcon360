"""
app/wallet/services/agent_statement_service.py

Generates an agent statement for a given period from the float ledger,
commissions earned, and payouts disbursed. The float ledger is the source of
truth for movement; commissions/payouts provide the earnings view.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional

from app.extensions import db
from app.wallet.models.agent_float import AgentFloatLedger
from app.wallet.models.commission import AgentCommission
from app.wallet.models.payout import PayoutRequest


class AgentStatementService:
    def __init__(self, session=None):
        self.db = session or db.session

    def generate(
        self,
        user_id: int,
        currency: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if to_date is None:
            to_date = datetime.now(timezone.utc)

        if from_date is None:
            from_date = datetime(to_date.year, to_date.month, 1, tzinfo=timezone.utc)

        ledger_q = (
            self.db.query(AgentFloatLedger)
            .filter(
                AgentFloatLedger.agent_user_id == user_id,
                AgentFloatLedger.currency == currency,
                AgentFloatLedger.is_deleted == False,
            )
        )

        opening = (
            ledger_q.filter(AgentFloatLedger.created_at < from_date)
            .order_by(AgentFloatLedger.created_at.desc())
            .first()
        )

        opening_balance = Decimal(str(opening.balance_after)) if opening else Decimal("0")

        period_entries = (
            ledger_q.filter(
                AgentFloatLedger.created_at >= from_date,
                AgentFloatLedger.created_at <= to_date,
            )
            .order_by(AgentFloatLedger.created_at.asc())
            .all()
        )

        cash_in = Decimal("0")
        refunds = Decimal("0")
        topups = Decimal("0")
        recalls = Decimal("0")
        line_items = []

        for e in period_entries:
            amt = Decimal(str(e.amount))
            line_items.append(
                {
                    "created_at": e.created_at.isoformat(),
                    "entry_type": e.entry_type,
                    "amount": str(amt),
                    "balance_after": str(e.balance_after),
                    "reference": e.reference,
                    "note": e.note,
                }
            )

            if e.entry_type == "cash_in":
                cash_in -= amt
            elif e.entry_type == "cash_in_refund":
                refunds += amt
            elif e.entry_type == "topup":
                topups += amt
            elif e.entry_type == "recall":
                recalls -= amt

        if period_entries:
            closing_balance = Decimal(str(period_entries[-1].balance_after))
        else:
            closing_balance = opening_balance

        commissions = (
            self.db.query(AgentCommission)
            .filter(
                AgentCommission.agent_id == user_id,
                AgentCommission.currency == currency,
                AgentCommission.is_deleted == False,
                AgentCommission.created_at >= from_date,
                AgentCommission.created_at <= to_date,
            )
            .all()
        )

        commission_earned = sum(
            (Decimal(str(c.amount)) for c in commissions), Decimal("0")
        )

        payouts = (
            self.db.query(PayoutRequest)
            .filter(
                PayoutRequest.agent_id == user_id,
                PayoutRequest.currency == currency,
                PayoutRequest.is_deleted == False,
                PayoutRequest.created_at >= from_date,
                PayoutRequest.created_at <= to_date,
            )
            .all()
        )

        payout_paid = sum(
            (Decimal(str(p.amount)) for p in payouts if p.status == "paid"),
            Decimal("0"),
        )

        return {
            "user_id": user_id,
            "currency": currency,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "opening_balance": str(opening_balance),
            "closing_balance": str(closing_balance),
            "cash_in_volume": str(cash_in),
            "refund_volume": str(refunds),
            "topup_volume": str(topups),
            "recall_volume": str(recalls),
            "commission_earned": str(commission_earned),
            "payout_paid": str(payout_paid),
            "line_items": line_items,
        }