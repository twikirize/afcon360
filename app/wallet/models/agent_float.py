"""
app/wallet/models/agent_float.py

Agent pre-funded digital float (GLOBAL_FUNDS_ARCHITECTURE.md Scenario C).

When an authorized agent confirms a physical cash-in, the system DEBITS the
agent's float and CREDITS the user's wallet. The float is the agent's stake
with AFCON360. One float row per (agent, currency).
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Numeric,
    DateTime,
    UniqueConstraint,
    Index,
    Text,
)
from app.models.base import BaseModel
from app.extensions import db


class AgentFloatAccount(BaseModel):
    __tablename__ = "agent_float_accounts"

    user_id = Column(
        BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    currency = Column(String(10), nullable=False)

    balance = Column(Numeric(20, 4), nullable=False, default=0)

    held = Column(Numeric(20, 4), nullable=False, default=0)

    last_settled_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "currency", name="uq_agent_float_user_currency"),
        Index("ix_agent_float_user", "user_id"),
    )

    def __repr__(self):
        return f"<AgentFloatAccount user={self.user_id} {self.currency} bal={self.balance}>"


class AgentFloatLedger(BaseModel):
    """
    Immutable movement ledger for an agent float account.

    Every debit/credit to the float (cash-in, refund, top-up, recall,
    settlement, adjustment) is recorded here with the resulting balance, so
    agent statements and reconciliation can be produced without mutating the
    account row.
    """

    __tablename__ = "agent_float_ledgers"

    float_account_id = Column(
        BigInteger,
        db.ForeignKey("agent_float_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )

    agent_user_id = Column(
        BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    currency = Column(String(10), nullable=False)

    amount = Column(Numeric(20, 4), nullable=False)

    balance_after = Column(Numeric(20, 4), nullable=False)

    entry_type = Column(String(30), nullable=False)

    reference = Column(String(64), nullable=True, index=True)

    created_by = Column(
        BigInteger,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    note = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_agent_float_ledger_account", "float_account_id"),
        Index("ix_agent_float_ledger_agent", "agent_user_id"),
        Index("ix_agent_float_ledger_created", "created_at"),
    )

    def __repr__(self):
        return f"<AgentFloatLedger acct={self.float_account_id} {self.entry_type} {self.amount} {self.currency}>"