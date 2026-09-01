"""
app/wallet/services/agent_float_service.py

Agent float balance operations. The float is the agent's pre-funded digital
stake with AFCON360 (GLOBAL_FUNDS_ARCHITECTURE.md Scenario C). A cash-in DEBITS
the float; a top-up/settlement CREDITS it.
"""

from decimal import Decimal
from typing import Optional
from datetime import datetime, timezone

from app.extensions import db
from app.wallet.repositories.agent_float_repository import AgentFloatRepository


class AgentFloatService:
    def __init__(self, session=None):
        self.db = session or db.session
        self.repo = AgentFloatRepository(self.db)

    def get_or_create(self, user_id: int, currency: str):
        return self.repo.get_or_create(user_id, currency)

    def get_balance(self, user_id: int, currency: str) -> Decimal:
        fa = self.repo.get(user_id, currency)
        if fa:
            return fa.balance
        return Decimal("0")

    def debit(
        self,
        user_id: int,
        currency: str,
        amount: Decimal,
        entry_type: str = "adjustment",
        reference: Optional[str] = None,
        created_by: Optional[int] = None,
        note: Optional[str] = None,
    ) -> Decimal:
        amount = Decimal(amount)
        if amount <= 0:
            raise ValueError("Debit amount must be positive")

        fa = self.repo.get_locked(user_id, currency)
        if fa is None:
            raise ValueError("Agent float account not found")

        if fa.balance < amount:
            raise ValueError(
                f"Insufficient agent float: have {fa.balance} {currency}, need {amount} {currency}"
            )

        fa.balance -= amount
        fa.updated_at = datetime.now(timezone.utc)

        self.db.flush()

        self.repo.record_ledger(
            float_account_id=int(fa.id),
            agent_user_id=user_id,
            currency=currency,
            amount=-amount,
            balance_after=fa.balance,
            entry_type=entry_type,
            reference=reference,
            created_by=created_by,
            note=note,
        )

        return fa.balance

    def credit(
        self,
        user_id: int,
        currency: str,
        amount: Decimal,
        entry_type: str = "adjustment",
        reference: Optional[str] = None,
        created_by: Optional[int] = None,
        note: Optional[str] = None,
    ) -> Decimal:
        amount = Decimal(amount)
        if amount < 0:
            raise ValueError("Credit amount must be non-negative")

        fa = self.repo.get_locked(user_id, currency)
        if fa is None:
            fa = self.repo.get_or_create(user_id, currency)

        fa.balance += amount
        fa.updated_at = datetime.now(timezone.utc)

        self.db.flush()

        self.repo.record_ledger(
            float_account_id=int(fa.id),
            agent_user_id=user_id,
            currency=currency,
            amount=amount,
            balance_after=fa.balance,
            entry_type=entry_type,
            reference=reference,
            created_by=created_by,
            note=note,
        )

        return fa.balance

    def ledgers_for(
        self,
        user_id: int,
        currency: str,
        limit: int = 200,
        offset: int = 0,
    ):
        return self.repo.ledgers_for(user_id, currency, limit=limit, offset=offset)