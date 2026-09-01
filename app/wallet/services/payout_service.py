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
from datetime import datetime, timezone
from flask import current_app

from app.extensions import db
from app.wallet.repositories.payout_repository import PayoutRepository
from app.wallet.models.ledger import AccountModel, AccountOwnerType, AccountStatus, AccountType
from app.audit.forensic_audit import ForensicAuditService


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
        available = self.available_commission(agent_id)
        return {
            'agent_id': agent_id,
            'total_pending': str(total_pending),
            'total_paid': str(total_paid),
            'available_commission': str(available),
        }

    def available_commission(self, agent_id: int, currency: str = 'UGX') -> Decimal:
        """Commission earned but not yet paid out, for an agent."""
        from app.wallet.models.commission import AgentCommission
        rows = (
            self.db.query(AgentCommission)
            .filter(
                AgentCommission.agent_id == agent_id,
                AgentCommission.currency == currency,
                AgentCommission.status != 'paid',
                AgentCommission.is_deleted == False,
            )
            .all()
        )
        return sum((Decimal(str(r.amount)) for r in rows), Decimal('0'))

    def request_for_agent(
        self,
        agent_id: int,
        amount: Decimal,
        currency: str,
        payment_method: str,
        payment_details: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Agent requests a payout of earned commission. Rejected if it exceeds
        available (unpaid) commission."""
        amount = Decimal(amount)
        available = self.available_commission(agent_id, currency)
        if amount <= 0:
            return {'success': False, 'error': 'Payout amount must be positive.'}
        if amount > available + Decimal('0.01'):
            return {
                'success': False,
                'error': 'Requested amount exceeds available commission.',
                'available': str(available),
            }
        result = self.create_request(
            agent_id=agent_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            payment_details=payment_details,
            metadata=metadata or {},
        )
        return {'success': True, **result}

    def get(self, request_ref: str):
        return self.repo.get(request_ref)

    def approve(self, request_ref: str, admin_user) -> Dict[str, Any]:
        pr = self.repo.get(request_ref)
        if not pr:
            return {'success': False, 'error': 'Payout request not found.'}
        if pr.status != 'pending':
            return {'success': False, 'error': f'Payout is already {pr.status}.'}
        pr.status = 'approved'
        pr.approved_by = int(admin_user.id)
        pr.approved_at = datetime.now(timezone.utc)
        self.db.add(pr)
        self.db.flush()
        return {'success': True, 'request_ref': request_ref, 'status': 'approved'}

    def reject(self, request_ref: str, admin_user, reason: str) -> Dict[str, Any]:
        pr = self.repo.get(request_ref)
        if not pr:
            return {'success': False, 'error': 'Payout request not found.'}
        if pr.status in ('paid', 'rejected'):
            return {'success': False, 'error': f'Payout is already {pr.status}.'}
        pr.status = 'rejected'
        pr.rejection_reason = reason
        self.db.add(pr)
        self.db.flush()
        return {'success': True, 'request_ref': request_ref, 'status': 'rejected'}

    def pay(self, request_ref: str, admin_user) -> Dict[str, Any]:
        """Settle a payout: mark paid, settle commission earnings, and disburse.

        - method == 'wallet': seamlessly credit the agent's AFCON360 user wallet
          (double-entry via WalletService.deposit). Seamless, no external provider.
        - method in ('bank','mobile_money'): external disbursement is a provider
          integration (deferred node). The owner/admin completes the transfer
          out-of-band; this records the internal settlement so commission cannot
          be re-paid.
        Every action is forensically audited.
        """
        pr = self.repo.get(request_ref)
        if not pr:
            return {'success': False, 'error': 'Payout request not found.'}
        if pr.status == 'paid':
            return {'success': False, 'error': 'Payout already paid.'}
        if pr.status == 'rejected':
            return {'success': False, 'error': 'Cannot pay a rejected payout.'}

        audit_id = self._audit_attempt(admin_user, pr, 'pay')
        try:
            disbursed_to = pr.payment_method
            note = ''
            if pr.payment_method == 'wallet':
                # Disburse first: a failure leaves the payout unpaid (no lost funds).
                self._disburse_to_wallet(pr)
            else:
                note = ("External disbursement (bank/mobile money) is completed by the "
                        "owner/admin out-of-band; internal settlement recorded.")

            # Settle unpaid commissions for this agent/currency up to the payout amount.
            from app.wallet.repositories.commission_repository import CommissionRepository
            CommissionRepository(self.db).settle_for_payout(pr.agent_id, pr.currency, pr.amount)

            pr.status = 'paid'
            pr.paid_by = int(admin_user.id)
            pr.paid_at = datetime.now(timezone.utc)
            if note:
                pr.notes = (pr.notes or '') + f"\n[Disbursement] {note}"
            self.db.add(pr)
            self.db.flush()
            self._audit_done(audit_id, 'completed', admin_user, note,
                            {'request_ref': request_ref, 'method': pr.payment_method})
            return {'success': True, 'request_ref': request_ref, 'status': 'paid',
                    'disbursed_to': disbursed_to}
        except Exception as e:
            self._audit_done(audit_id, 'failed', admin_user, str(e))
            current_app.logger.exception("Payout pay failed")
            return {'success': False, 'error': f'Payout settlement failed: {e}'}

    # ---- helpers -------------------------------------------------------------

    def _ensure_user_account(self, user_id: int, currency: str) -> AccountModel:
        """Return the agent's user wallet account, creating it if necessary."""
        acct = AccountModel.query.filter_by(
            user_id=int(user_id), owner_type=AccountOwnerType.USER
        ).first()
        if not acct:
            acct = AccountModel(
                id=str(uuid4()),
                user_id=int(user_id),
                currency=currency,
                is_frozen=False,
                frozen_reason=None,
                frozen_at=None,
                daily_volume=Decimal('0'),
                daily_volume_reset_at=None,
                monthly_volume=Decimal('0'),
                monthly_volume_reset_at=None,
                owner_type=AccountOwnerType.USER,
                status=AccountStatus.ACTIVE,
                account_type=AccountType.USER_WALLET,
                account_name=f"Wallet_{currency}_{user_id}",
                verified=False,
            )
            self.db.add(acct)
            self.db.flush()
        return acct

    def _disburse_to_wallet(self, pr) -> None:
        """Credit the agent's AFCON360 user wallet with the payout amount."""
        from app.wallet.services.wallet_service import WalletService

        ws = WalletService(self.db)
        acct = self._ensure_user_account(pr.agent_id, pr.currency)
        ws.deposit(
            account_id=str(acct.id),
            amount=pr.amount,
            currency=pr.currency,
            client_request_id=f"PAYOUT-{pr.request_ref}",
            reference=pr.request_ref,
            idempotency_key=pr.request_ref,
            payment_method="agent_commission_payout",
            payment_provider="afcon360_wallet",
            metadata={
                "source": "agent_commission_payout",
                "request_ref": pr.request_ref,
                "agent_id": int(pr.agent_id),
            },
            actor_id=pr.paid_by or int(pr.agent_id),
        )

    def _audit_attempt(self, admin_user, pr, action: str):
        try:
            return ForensicAuditService.log_attempt(
                entity_type="agent_payout",
                entity_id=str(pr.request_ref),
                action=action,
                user_id=getattr(admin_user, "id", None),
                details={"agent_id": int(pr.agent_id), "amount": str(pr.amount),
                         "currency": pr.currency, "method": pr.payment_method},
                risk_score=40,
            )
        except Exception:
            current_app.logger.exception("Agent payout audit attempt failed")
            return None

    def _audit_done(self, audit_id, status: str, admin_user, notes: str, result: dict):
        if not audit_id:
            return
        try:
            ForensicAuditService.log_completion(
                audit_id=audit_id,
                status=status,
                reviewed_by=getattr(admin_user, "id", None),
                review_notes=notes or "",
                result_details=result or {},
            )
        except Exception:
            current_app.logger.exception("Agent payout audit completion failed")

