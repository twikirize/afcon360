"""
app/wallet/services/agent_refund_service.py

Agent Cash-In refund (GLOBAL_FUNDS_ARCHITECTURE.md Scenario C).

A refund reverses a previously confirmed cash-in:
  - the customer's wallet credit is reversed (system-initiated internal debit),
  - the agent's float stake is returned to them,
  - the original cash-in transaction is marked refunded,
  - a forensic audit entry is recorded.

Idempotent: re-submitting the same reference returns the existing refund result.
"""

from decimal import Decimal
from typing import Dict, Any, Optional

from flask import current_app
from app.extensions import db
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.agent_float_service import AgentFloatService
from app.wallet.models.transaction import TransactionModel
from app.audit.comprehensive_audit import AuditService


class AgentRefundService:
    def __init__(self, session=None):
        self.db = session or db.session

    def _agents_enabled(self) -> bool:
        try:
            from app.wallet.models.config import WalletSystemConfig
            return bool(WalletSystemConfig.get_config().agents_enabled)
        except Exception:
            return False

    def get_original(self, reference: str) -> Optional[TransactionModel]:
        return (
            self.db.query(TransactionModel)
            .filter(
                TransactionModel.external_reference == reference,
                TransactionModel.tx_metadata["source"].astext == "agent_cash_in",
                TransactionModel.is_deleted == False,
            )
            .order_by(TransactionModel.created_at.desc())
            .first()
        )

    def refund(
        self,
        reference: str,
        actor_user: Any,
    ) -> Dict[str, Any]:
        if not self._agents_enabled():
            return {"success": False, "error": "Agent cash-in is currently disabled."}

        original = self.get_original(reference)
        if not original:
            return {"success": False, "error": "No agent cash-in found for this reference."}

        meta = original.tx_metadata or {}
        agent_id = meta.get("agent_id")
        if not agent_id:
            return {"success": False, "error": "Original cash-in has no linked agent."}

        if meta.get("refunded"):
            return {
                "success": True,
                "already_refunded": True,
                "reference": reference,
                "amount": str(original.amount),
                "currency": original.currency,
            }

        amount = Decimal(str(original.amount))
        currency = str(original.currency)
        account_id = original.account_id
        customer_id = original.user_id

        wallet_service = WalletService(self.db)
        float_service = AgentFloatService(self.db)
        actor_id = int(actor_user.id)

        is_agent_self = int(agent_id) == actor_id
        is_privileged = getattr(actor_user, "is_super_admin", False) or getattr(actor_user, "is_owner", False)

        if not is_agent_self and not is_privileged:
            return {"success": False, "error": "You are not authorized to refund this cash-in."}

        try:
            with self.db.begin():
                if account_id and customer_id:
                    wallet_service.admin_withdraw(
                        account_id=str(account_id),
                        amount=amount,
                        currency=currency,
                        reason=f"Agent cash-in refund (internal reversal) ref={reference}",
                    )

                float_service.credit(
                    int(agent_id),
                    currency,
                    amount,
                    entry_type="cash_in_refund",
                    reference=reference,
                    created_by=actor_id,
                    note=f"Refund of cash-in {reference}",
                )

                original.status = "cancelled"
                meta["refunded"] = True
                meta["refunded_by"] = actor_id
                original.tx_metadata = meta

                self.db.add(original)

        except (KeyError, TypeError, ValueError) as e:
            return {"success": False, "error": f"Malformed original cash-in: {e}"}
        except Exception as e:
            current_app.logger.exception("Agent cash-in refund failed")
            return {"success": False, "error": f"Refund failed: {e}"}

        try:
            AuditService.financial(
                transaction_id=f"AGT-RFD-{reference}",
                transaction_type="refund",
                amount=amount,
                currency=currency,
                status="completed",
                from_user_id=customer_id,
                to_user_id=int(agent_id),
                payment_method="agent_cash_in_refund",
                payment_provider="afcon360_agent",
                external_reference=reference,
                metadata={"actor_id": actor_id, "stage": "agent_refund"},
            )
        except Exception:
            current_app.logger.exception("Agent refund audit failed")

        return {
            "success": True,
            "reference": reference,
            "amount": str(amount),
            "currency": currency,
            "agent_id": int(agent_id),
        }