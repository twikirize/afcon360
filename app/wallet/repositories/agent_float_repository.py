"""
app/wallet/repositories/agent_float_repository.py

Data access for AgentFloatAccount.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from app.extensions import db
from app.wallet.models.agent_float import AgentFloatAccount, AgentFloatLedger


class AgentFloatRepository:
    def __init__(self, session=None):
        self.db = session or db.session

    def get(self, user_id: int, currency: str) -> Optional[AgentFloatAccount]:
        return (
            self.db.query(AgentFloatAccount)
            .filter(
                AgentFloatAccount.user_id == user_id,
                AgentFloatAccount.currency == currency,
                AgentFloatAccount.is_deleted == False,
            )
            .first()
        )

    def get_locked(self, user_id: int, currency: str) -> Optional[AgentFloatAccount]:
        return (
            self.db.query(AgentFloatAccount)
            .filter(
                AgentFloatAccount.user_id == user_id,
                AgentFloatAccount.currency == currency,
                AgentFloatAccount.is_deleted == False,
            )
            .with_for_update()
            .first()
        )

    def get_or_create(self, user_id: int, currency: str) -> AgentFloatAccount:
        existing = self.get(user_id, currency)
        if existing:
            return existing

        float_account = AgentFloatAccount(
            user_id=user_id,
            currency=currency,
            balance=Decimal("0"),
            held=Decimal("0"),
        )
        self.db.add(float_account)
        self.db.flush()
        return float_account

    def record_ledger(
        self,
        float_account_id: int,
        agent_user_id: int,
        currency: str,
        amount: Decimal,
        balance_after: Decimal,
        entry_type: str,
        reference: Optional[str] = None,
        created_by: Optional[int] = None,
        note: Optional[str] = None,
    ) -> AgentFloatLedger:
        entry = AgentFloatLedger(
            float_account_id=float_account_id,
            agent_user_id=agent_user_id,
            currency=currency,
            amount=amount,
            balance_after=balance_after,
            entry_type=entry_type,
            reference=reference,
            created_by=created_by,
            note=note,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def ledgers_for(
        self,
        user_id: int,
        currency: str,
        limit: int = 200,
        offset: int = 0,
    ) -> list[AgentFloatLedger]:
        return (
            self.db.query(AgentFloatLedger)
            .filter(
                AgentFloatLedger.agent_user_id == user_id,
                AgentFloatLedger.currency == currency,
                AgentFloatLedger.is_deleted == False,
            )
            .order_by(AgentFloatLedger.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )