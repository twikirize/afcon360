"""
app/wallet/services/agent_cashin_service.py

Completes an Agent Cash-In (GLOBAL_FUNDS_ARCHITECTURE.md Scenario C):

    user generates reference code  ->  (out of band) hands cash + code to agent
    ->  agent confirms code in Agent Portal
    ->  system DEBITS agent float, CREDITS user wallet, records commission,
        notifies user, audits. Idempotent via the deposit intent + ledger
        idempotency key.

Anti-inflation guarantee: the user's wallet is NEVER credited on submit; only
on authorized agent confirmation (debit of pre-funded float).
"""

import uuid
from decimal import Decimal
from typing import Dict, Any, Optional

from flask import current_app
from app.extensions import db
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.agent_float_service import AgentFloatService
from app.wallet.services.deposit_intent import get_deposit_intent, consume_deposit_intent
from app.audit.comprehensive_audit import AuditService, TransactionType


class AgentCashInService:
    def __init__(self, session=None):
        self.db = session or db.session

    def _agents_enabled(self) -> bool:
        try:
            from app.wallet.models.config import WalletSystemConfig
            return bool(WalletSystemConfig.get_config().agents_enabled)
        except Exception:
            return False

    def confirm(
        self,
        reference: str,
        agent_user: Any,
    ) -> Dict[str, Any]:
        if not getattr(agent_user, "is_agent", False):
            return {"success": False, "error": "Only authorized agents can confirm cash-ins."}

        if not self._agents_enabled():
            return {"success": False, "error": "Agent cash-in is currently disabled."}

        intent = get_deposit_intent(reference)
        if not intent:
            return {"success": False, "error": "Invalid or expired reference code."}

        if intent.get("source") != "agent":
            return {"success": False, "error": "This reference is not an agent deposit."}

        amount = Decimal(str(intent.get("amount")))
        currency = str(intent.get("currency"))
        user_id = int(intent.get("user_id"))
        account_id = intent.get("account_id")

        agent_id = int(agent_user.id)

        from app.wallet.services.agent_terms_service import assert_agent_can_operate

        guard = assert_agent_can_operate(agent_user, currency, amount, "cashin")
        if not guard.get("ok"):
            return {"success": False, "error": guard.get("error")}

        float_service = AgentFloatService(self.db)
        wallet_service = WalletService(self.db)

        try:
            with self.db.begin():
                float_service.debit(
                    agent_id,
                    currency,
                    amount,
                    entry_type="cash_in",
                    reference=reference,
                    created_by=agent_id,
                )

                result = wallet_service.deposit(
                    account_id=account_id,
                    amount=amount,
                    currency=currency,
                    system_initiated=True,
                    payment_method="agent_cash_in",
                    payment_provider="afcon360_agent",
                    metadata={
                        "agent_id": agent_id,
                        "agent_code": getattr(agent_user, "agent_code", None),
                        "source": "agent_cash_in",
                        "reference": reference,
                    },
                    reference=reference,
                    idempotency_key=reference,
                )

        except (KeyError, TypeError, ValueError) as e:
            return {"success": False, "error": f"Malformed deposit intent: {e}"}
        except ValueError as e:
            current_app.logger.error(f"Agent cash-in wallet credit failed, refunding float: {e}")
            try:
                with self.db.begin():
                    float_service.credit(agent_id, currency, amount)
            except Exception:
                current_app.logger.exception("Failed to refund agent float after deposit error")
            return {"success": False, "error": f"Could not credit wallet: {e}"}
        except Exception as e:
            current_app.logger.exception("Agent cash-in failed")
            try:
                with self.db.begin():
                    float_service.credit(agent_id, currency, amount)
            except Exception:
                current_app.logger.exception("Failed to refund agent float after deposit error")
            return {"success": False, "error": f"Could not credit wallet: {e}"}

        try:
            consume_deposit_intent(reference)
        except Exception:
            current_app.logger.warning(f"Could not consume deposit intent {reference}")

        try:
            AuditService.financial(
                transaction_id=f"AGT-{uuid.uuid4().hex[:12].upper()}",
                transaction_type=TransactionType.DEPOSIT,
                amount=amount,
                currency=currency,
                status="completed",
                from_user_id=agent_id,
                to_user_id=user_id,
                payment_method="agent_cash_in",
                payment_provider="afcon360_agent",
                external_reference=reference,
                metadata={
                    "agent_code": getattr(agent_user, "agent_code", None),
                    "reference": reference,
                    "stage": "agent_confirmed",
                },
            )
        except Exception:
            current_app.logger.exception("Agent cash-in financial audit failed")

        return {
            "success": True,
            "new_balance": result.get("new_balance"),
            "amount": str(amount),
            "currency": currency,
            "reference": reference,
        }

    def add_float(
        self,
        agent_user: Any,
        amount: Decimal,
        currency: str,
    ) -> Dict[str, Any]:
        if not getattr(agent_user, "is_agent", False):
            return {"success": False, "error": "Only authorized agents can manage float."}

        amount = Decimal(amount)
        if amount <= 0:
            return {"success": False, "error": "Top-up amount must be positive."}

        float_service = AgentFloatService(self.db)
        agent_id = int(agent_user.id)

        try:
            with self.db.begin():
                new_balance = float_service.credit(
                    agent_id,
                    currency,
                    amount,
                    entry_type="topup",
                    created_by=agent_id,
                )
        except Exception as e:
            return {"success": False, "error": str(e)}

        return {
            "success": True,
            "new_balance": str(new_balance),
            "currency": currency,
        }