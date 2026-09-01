"""
app/wallet/services/agent_cashout_service.py

Completes an Agent Cash-Out (user withdrawal handled by an agent):

    user generates WDR- reference  ->  (out of band) hands code to agent and
    receives physical cash
    ->  agent confirms code in Agent Portal
    ->  system DEBITS user wallet, CREDITS agent float, records commission,
        notifies, audits. Idempotent via the withdrawal intent + ledger
        idempotency key.

Double-entry is preserved: the user's wallet DEBIT is matched by the agent's
float CREDIT (the cash the agent disbursed, which AFCON360 now owes the agent).
Any platform withdrawal fee is booked separately by WalletService, keeping the
ledger balanced.
"""

import uuid
from decimal import Decimal
from typing import Any, Dict

from flask import current_app
from app.extensions import db
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.agent_float_service import AgentFloatService
from app.wallet.services.withdrawal_intent import get_withdrawal_intent, consume_withdrawal_intent
from app.wallet.services.agent_terms_service import assert_agent_can_operate, get_direction_terms
from app.wallet.services.commission_service import CommissionService
from app.audit.comprehensive_audit import AuditService, TransactionType


class AgentCashOutService:
    def __init__(self, session=None):
        self.db = session or db.session

    def confirm(
        self,
        reference: str,
        agent_user: Any,
    ) -> Dict[str, Any]:
        if not getattr(agent_user, "is_agent", False):
            return {"success": False, "error": "Only authorized agents can confirm cash-outs."}

        intent = get_withdrawal_intent(reference)
        if not intent:
            return {"success": False, "error": "Invalid or expired reference code."}

        if intent.get("source") != "agent_cashout":
            return {"success": False, "error": "This reference is not an agent withdrawal."}

        amount = Decimal(str(intent.get("amount")))
        currency = str(intent.get("currency"))
        user_id = int(intent.get("user_id"))
        account_id = intent.get("account_id")

        from app.wallet.services.agent_terms_service import assert_agent_can_operate

        guard = assert_agent_can_operate(agent_user, currency, amount, "cashout")
        if not guard.get("ok"):
            return {"success": False, "error": guard.get("error")}

        agent_id = int(agent_user.id)
        agent_code = getattr(agent_user, "agent_code", None)

        wallet_service = WalletService(self.db)

        try:
            withdraw_result = wallet_service.withdraw(
                account_id=account_id,
                amount=amount,
                currency=currency,
                client_request_id=reference,
                metadata={
                    "agent_id": agent_id,
                    "source": "agent_cash_out",
                    "reference": reference,
                    "agent_code": agent_code,
                },
                payment_method="agent_cash_out",
                payment_provider="afcon360_agent",
                actor_id=agent_id,
                agent_on_behalf=True,
            )
        except (KeyError, TypeError, ValueError) as e:
            return {"success": False, "error": f"Malformed withdrawal intent: {e}"}
        except Exception as e:
            current_app.logger.error(f"Agent cash-out wallet debit failed: {e}")
            return {"success": False, "error": f"Could not debit user wallet: {e}"}

        float_service = AgentFloatService(self.db)

        try:
            with self.db.begin():
                new_balance = float_service.credit(
                    agent_id,
                    currency,
                    amount,
                    entry_type="cash_out",
                    reference=reference,
                    created_by=agent_id,
                )
        except Exception:
            current_app.logger.exception("Agent cash-out float credit failed after wallet debit; reconcile manually")
            return {
                "success": True,
                "new_balance": None,
                "amount": str(amount),
                "currency": currency,
                "reference": reference,
                "warning": "Float credit pending reconciliation",
            }

        try:
            consume_withdrawal_intent(reference)
        except Exception:
            current_app.logger.warning(f"Could not consume withdrawal intent {reference}")

        # Commission
        rate = Decimal(str(get_direction_terms("cashout").get("commission_rate", 0))) / Decimal("100")
        commission_amt = (amount * rate).quantize(Decimal("0.000001"))

        if commission_amt > 0:
            source_id = None
            if isinstance(withdraw_result, dict):
                source_id = withdraw_result.get("transaction_id")
            if not source_id:
                source_id = str(uuid.uuid4())

            try:
                CommissionService(self.db).record_commission(
                    agent_id=agent_id,
                    amount=commission_amt,
                    currency=currency,
                    source_type="cash_out",
                    source_id=source_id,
                    recipient_id=user_id,
                    extra_data={"reference": reference, "agent_code": agent_code},
                )
            except Exception:
                current_app.logger.exception("Agent cash-out commission recording failed")

        # Audit
        try:
            AuditService.financial(
                transaction_id=f"AGT-{uuid.uuid4().hex[:12].upper()}",
                transaction_type=TransactionType.WITHDRAW,
                amount=amount,
                currency=currency,
                status="completed",
                from_user_id=user_id,
                to_user_id=agent_id,
                payment_method="agent_cash_out",
                payment_provider="afcon360_agent",
                external_reference=reference,
                metadata={
                    "agent_code": agent_code,
                    "reference": reference,
                    "stage": "agent_confirmed",
                },
            )
        except Exception:
            current_app.logger.exception("Agent cash-out financial audit failed")

        return {
            "success": True,
            "new_balance": str(new_balance),
            "amount": str(amount),
            "currency": currency,
            "reference": reference,
        }