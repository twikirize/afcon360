"""
app/wallet/services/agent_reconciliation_service.py

Per-agent reconciliation for the agent float system. For every agent float
account it verifies:

  * the stored float balance equals the signed sum of its ledger entries
    (float debits/credits are always balanced by ledger movement), and
  * requested payouts do not exceed earned-and-unpaid commissions
    (over-claim / suspicious payout monitoring).

Mismatches are recorded as ReconciliationIssue rows attached to a
ReconciliationRun, mirroring the platform reconciliation pattern.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional

from flask import current_app
from app.extensions import db
from app.wallet.models.agent_float import AgentFloatAccount, AgentFloatLedger
from app.wallet.models.commission import AgentCommission
from app.wallet.models.payout import PayoutRequest
from app.wallet.models.reconciliation import ReconciliationRun, ReconciliationIssue


class AgentReconciliationService:
    TOLERANCE = Decimal("0.01")

    def __init__(self, session=None):
        self.db = session or db.session

    def reconcile_all(self) -> Dict[str, Any]:
        run = ReconciliationRun(status="running")
        self.db.add(run)
        self.db.flush()

        accounts = (
            self.db.query(AgentFloatAccount)
            .filter(AgentFloatAccount.is_deleted == False)
            .all()
        )

        issues = []
        agents_checked = 0

        for acct in accounts:
            agents_checked += 1

            try:
                mismatch = self._check_float_balance(acct)
                if mismatch:
                    issues.append(mismatch)
                    self._record_issue(run.id, mismatch)

                payout_issue = self._check_payouts(acct)
                if payout_issue:
                    issues.append(payout_issue)
                    self._record_issue(run.id, payout_issue)

            except Exception:
                current_app.logger.exception("Agent reconciliation failed for account %s", acct.id)

        summary = {
            "scope": "agent_float",
            "agents_checked": agents_checked,
            "issues_found": len(issues),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        run.status = "completed"
        run.summary = summary
        run.completed_at = datetime.now(timezone.utc)
        self.db.flush()

        return {
            "success": True,
            "run_id": getattr(run, "id", None),
            "summary": summary,
            "issues": issues,
        }

    def _check_float_balance(self, acct: AgentFloatAccount) -> Optional[Dict[str, Any]]:
        rows = (
            self.db.query(AgentFloatLedger)
            .filter(
                AgentFloatLedger.float_account_id == acct.id,
                AgentFloatLedger.is_deleted == False,
            )
            .all()
        )

        expected = sum((Decimal(str(r.amount)) for r in rows), Decimal("0"))
        stored = Decimal(str(acct.balance))

        if abs(expected - stored) > self.TOLERANCE:
            return {
                "issue_type": "agent_float_imbalance",
                "details": {
                    "agent_user_id": acct.user_id,
                    "currency": acct.currency,
                    "ledger_expected": str(expected),
                    "stored_balance": str(stored),
                    "difference": str(expected - stored),
                },
            }
        return None

    def _check_payouts(self, acct: AgentFloatAccount) -> Optional[Dict[str, Any]]:
        earned = (
            self.db.query(AgentCommission)
            .filter(
                AgentCommission.agent_id == acct.user_id,
                AgentCommission.currency == acct.currency,
                AgentCommission.is_deleted == False,
            )
            .all()
        )

        unpaid = sum((Decimal(str(c.amount)) for c in earned if c.status != "paid"), Decimal("0"))

        pending_payouts = (
            self.db.query(PayoutRequest)
            .filter(
                PayoutRequest.agent_id == acct.user_id,
                PayoutRequest.currency == acct.currency,
                PayoutRequest.status.in_(["pending", "approved"]),
                PayoutRequest.is_deleted == False,
            )
            .all()
        )

        requested = sum((Decimal(str(p.amount)) for p in pending_payouts), Decimal("0"))

        if requested > unpaid + self.TOLERANCE:
            return {
                "issue_type": "agent_payout_overclaim",
                "details": {
                    "agent_user_id": acct.user_id,
                    "currency": acct.currency,
                    "unpaid_commissions": str(unpaid),
                    "requested_payouts": str(requested),
                    "excess": str(requested - unpaid),
                },
            }
        return None

    def _record_issue(self, run_id: int, mismatch: Dict[str, Any]) -> None:
        issue = ReconciliationIssue(
            run_id=run_id,
            issue_type=mismatch["issue_type"],
            details=mismatch["details"],
            resolved="no",
        )
        self.db.add(issue)
        self.db.flush()