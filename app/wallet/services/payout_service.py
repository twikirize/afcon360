"""
app/wallet/services/payout_service.py
Agent payout request management - Database backed with full audit trails.
"""

from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Dict, Any
from flask import current_app, request
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.wallet.models import PayoutRequest
from app.wallet.exceptions import WalletError
from app.audit.comprehensive_audit import AuditService, AuditSeverity


class PayoutService:
    """
    Service for managing agent payout requests with full audit trails.

    Features:
    - Database persistence
    - Complete audit trail for all payout operations
    - Status workflow: pending → approved/rejected → paid
    - Integration with wallet for balance verification
    """

    def __init__(self):
        pass

    def create_request(
        self,
        agent_id: int,
        amount: Decimal,
        currency: str,
        payment_method: str,
        payment_details: Dict,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a new payout request with full audit trail.

        Args:
            agent_id: User ID of the agent
            amount: Amount to payout
            currency: Currency code
            payment_method: bank, mobile_money, cash
            payment_details: Account details (bank name, account number, etc.)
            idempotency_key: Unique key to prevent duplicate requests
            metadata: Additional data

        Returns:
            Dict with payout request record

        Raises:
            ValueError: If amount is invalid
            DuplicateTransactionError: If idempotency_key already used
        """
        from app.wallet.exceptions import DuplicateTransactionError
        import uuid

        if amount <= Decimal("0"):
            raise ValueError("Amount must be greater than zero")

        # Generate request reference
        request_ref = idempotency_key or f"PO-{uuid.uuid4().hex[:12].upper()}"

        # Check for duplicate by reference
        existing = PayoutRequest.query.filter_by(request_ref=request_ref).first()
        if existing:
            raise DuplicateTransactionError(request_ref, str(existing.id))

        # Get current commission total to verify sufficient funds
        from app.wallet.services.commission_service import CommissionService
        commission_service = CommissionService()
        pending_total = commission_service.get_pending_total(agent_id, currency)

        if pending_total < amount:
            raise ValueError(
                f"Insufficient pending commissions. Available: {pending_total} {currency}, "
                f"Requested: {amount} {currency}"
            )

        # Create audit record BEFORE database insert
        audit_id = f"AUD-{uuid.uuid4().hex[:12].upper()}"
        try:
            AuditService.data_change(
                entity_type="payout_request",
                entity_id=request_ref,
                operation="create",
                old_value=None,
                new_value={
                    "agent_id": agent_id,
                    "amount": float(amount),
                    "currency": currency,
                    "payment_method": payment_method,
                    "status": "pending"
                },
                changed_by=agent_id,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request else None,
                metadata={
                    "audit_id": audit_id,
                    "payment_details_type": payment_details.get('type', 'unknown'),
                    "client_metadata": metadata or {}
                }
            )
        except Exception as e:
            current_app.logger.error(f"Failed to create audit record: {e}")

        # Create database record
        try:
            payout = PayoutRequest(
                request_ref=request_ref,
                agent_id=agent_id,
                amount=amount,
                currency=currency.upper(),
                payment_method=payment_method,
                payment_details=payment_details,
                status="pending",
                metadata=metadata or {},
                created_at=datetime.utcnow()
            )

            db.session.add(payout)
            db.session.flush()  # Get ID without committing

            # Update audit with payout ID
            try:
                AuditService.data_change(
                    entity_type="payout_request",
                    entity_id=request_ref,
                    operation="create",
                    old_value=None,
                    new_value={"id": payout.id, "status": "pending"},
                    changed_by=agent_id,
                    metadata={"audit_id": audit_id, "payout_id": payout.id}
                )
            except Exception as e:
                current_app.logger.error(f"Failed to update audit: {e}")

            db.session.commit()

            current_app.logger.info(
                f"Payout request created: {request_ref} - agent={agent_id}, "
                f"amount={amount} {currency}"
            )

            return {
                "id": payout.id,
                "request_ref": payout.request_ref,
                "agent_id": payout.agent_id,
                "amount": str(payout.amount),
                "currency": payout.currency,
                "payment_method": payout.payment_method,
                "payment_details": payout.payment_details,
                "status": payout.status,
                "metadata": payout.metadata,
                "created_at": payout.created_at.isoformat(),
                "audit_id": audit_id
            }

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error creating payout request: {e}")
            raise WalletError(f"Failed to create payout request: {str(e)}")

    def get_request(self, request_id: int) -> Optional[Dict]:
        """Get a specific payout request by ID."""
        try:
            payout = PayoutRequest.query.get(request_id)
            if not payout:
                return None

            return {
                "id": payout.id,
                "request_ref": payout.request_ref,
                "agent_id": payout.agent_id,
                "amount": str(payout.amount),
                "currency": payout.currency,
                "payment_method": payout.payment_method,
                "payment_details": payout.payment_details,
                "status": payout.status,
                "approved_by": payout.approved_by,
                "approved_at": payout.approved_at.isoformat() if payout.approved_at else None,
                "paid_by": payout.paid_by,
                "paid_at": payout.paid_at.isoformat() if payout.paid_at else None,
                "rejection_reason": payout.rejection_reason,
                "notes": payout.notes,
                "metadata": payout.metadata,
                "created_at": payout.created_at.isoformat()
            }
        except Exception as e:
            current_app.logger.error(f"Error getting payout request {request_id}: {e}")
            return None

    def get_request_by_ref(self, request_ref: str) -> Optional[Dict]:
        """Get a specific payout request by reference."""
        try:
            payout = PayoutRequest.query.filter_by(request_ref=request_ref).first()
            if not payout:
                return None

            return self.get_request(payout.id)
        except Exception as e:
            current_app.logger.error(f"Error getting payout request by ref {request_ref}: {e}")
            return None

    def list_requests(
        self,
        agent_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """List payout requests with optional filters."""
        try:
            query = PayoutRequest.query

            if agent_id:
                query = query.filter_by(agent_id=agent_id)

            if status:
                query = query.filter_by(status=status)

            payouts = query.order_by(
                PayoutRequest.created_at.desc()
            ).offset(offset).limit(limit).all()

            return [
                {
                    "id": p.id,
                    "request_ref": p.request_ref,
                    "agent_id": p.agent_id,
                    "amount": str(p.amount),
                    "currency": p.currency,
                    "payment_method": p.payment_method,
                    "status": p.status,
                    "created_at": p.created_at.isoformat(),
                    "approved_at": p.approved_at.isoformat() if p.approved_at else None,
                    "paid_at": p.paid_at.isoformat() if p.paid_at else None,
                }
                for p in payouts
            ]
        except Exception as e:
            current_app.logger.error(f"Error listing payout requests: {e}")
            return []

    def approve_request(
        self,
        request_id: int,
        approved_by_user_id: int,
        notes: Optional[str] = None
    ) -> bool:
        """
        Approve a pending payout request.

        Args:
            request_id: ID of the payout request
            approved_by_user_id: Admin user ID who approves
            notes: Optional notes about approval

        Returns:
            True if successful
        """
        from flask import request

        try:
            payout = PayoutRequest.query.get(request_id)
            if not payout:
                raise WalletError(f"Payout request {request_id} not found")

            if payout.status != 'pending':
                raise WalletError(f"Cannot approve payout with status: {payout.status}")

            old_status = payout.status

            # Update payout
            payout.status = 'approved'
            payout.approved_by = approved_by_user_id
            payout.approved_at = datetime.utcnow()
            if notes:
                payout.notes = notes

            db.session.commit()

            # Audit the approval
            try:
                AuditService.data_change(
                    entity_type="payout_request",
                    entity_id=payout.request_ref,
                    operation="approve",
                    old_value={"status": old_status},
                    new_value={"status": "approved", "approved_by": approved_by_user_id},
                    changed_by=approved_by_user_id,
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    metadata={
                        "request_id": payout.id,
                        "agent_id": payout.agent_id,
                        "amount": float(payout.amount),
                        "notes": notes
                    }
                )

                AuditService.security(
                    event_type="payout_approved",
                    severity=AuditSeverity.INFO,
                    description=f"Payout request {payout.request_ref} approved",
                    user_id=payout.agent_id,
                    ip_address=request.remote_addr if request else None,
                    metadata={
                        "request_id": payout.id,
                        "amount": float(payout.amount),
                        "currency": payout.currency,
                        "approved_by": approved_by_user_id
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to audit approval: {e}")

            current_app.logger.info(
                f"Payout request {payout.request_ref} approved by user {approved_by_user_id}"
            )

            return True

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error approving payout: {e}")
            raise WalletError(f"Failed to approve payout: {str(e)}")

    def reject_request(
        self,
        request_id: int,
        rejected_by_user_id: int,
        reason: str
    ) -> bool:
        """
        Reject a pending payout request.

        Args:
            request_id: ID of the payout request
            rejected_by_user_id: Admin user ID who rejects
            reason: Reason for rejection

        Returns:
            True if successful
        """
        from flask import request

        try:
            payout = PayoutRequest.query.get(request_id)
            if not payout:
                raise WalletError(f"Payout request {request_id} not found")

            if payout.status != 'pending':
                raise WalletError(f"Cannot reject payout with status: {payout.status}")

            old_status = payout.status

            # Update payout
            payout.status = 'rejected'
            payout.rejection_reason = reason

            db.session.commit()

            # Audit the rejection
            try:
                AuditService.data_change(
                    entity_type="payout_request",
                    entity_id=payout.request_ref,
                    operation="reject",
                    old_value={"status": old_status},
                    new_value={"status": "rejected", "reason": reason},
                    changed_by=rejected_by_user_id,
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    metadata={
                        "request_id": payout.id,
                        "agent_id": payout.agent_id,
                        "amount": float(payout.amount),
                        "reason": reason
                    }
                )

                AuditService.security(
                    event_type="payout_rejected",
                    severity=AuditSeverity.WARNING,
                    description=f"Payout request {payout.request_ref} rejected: {reason}",
                    user_id=payout.agent_id,
                    ip_address=request.remote_addr if request else None,
                    metadata={
                        "request_id": payout.id,
                        "amount": float(payout.amount),
                        "currency": payout.currency,
                        "reason": reason,
                        "rejected_by": rejected_by_user_id
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to audit rejection: {e}")

            current_app.logger.info(
                f"Payout request {payout.request_ref} rejected by user {rejected_by_user_id}: {reason}"
            )

            return True

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error rejecting payout: {e}")
            raise WalletError(f"Failed to reject payout: {str(e)}")

    def mark_as_paid(
        self,
        request_id: int,
        paid_by_user_id: int,
        payment_reference: Optional[str] = None,
        notes: Optional[str] = None
    ) -> bool:
        """
        Mark an approved payout as paid.

        Args:
            request_id: ID of the payout request
            paid_by_user_id: Admin user ID who processed payment
            payment_reference: External payment reference
            notes: Optional notes about payment

        Returns:
            True if successful
        """
        from flask import request

        try:
            payout = PayoutRequest.query.get(request_id)
            if not payout:
                raise WalletError(f"Payout request {request_id} not found")

            if payout.status != 'approved':
                raise WalletError(f"Cannot mark payout as paid with status: {payout.status}")

            old_status = payout.status

            # Update payout
            payout.status = 'paid'
            payout.paid_by = paid_by_user_id
            payout.paid_at = datetime.utcnow()
            if payment_reference:
                payout.metadata = payout.metadata or {}
                payout.metadata['payment_reference'] = payment_reference
            if notes:
                payout.notes = payout.notes or ""
                payout.notes += f"\nPayment notes: {notes}"

            db.session.commit()

            # Mark associated commissions as paid
            from app.wallet.services.commission_service import CommissionService
            commission_service = CommissionService()

            # Get unpaid commissions for this agent
            unpaid_commissions = commission_service.get_unpaid_commissions_by_agent(
                payout.agent_id, payout.currency
            )

            # Mark commissions as paid up to the payout amount
            remaining = payout.amount
            for commission in unpaid_commissions:
                if remaining <= 0:
                    break
                commission_amount = Decimal(commission['amount'])
                if commission_amount <= remaining:
                    commission_service.mark_as_paid(
                        commission['id'],
                        paid_by_user_id,
                        f"Paid via payout {payout.request_ref}"
                    )
                    remaining -= commission_amount

            # Audit the payment
            try:
                AuditService.data_change(
                    entity_type="payout_request",
                    entity_id=payout.request_ref,
                    operation="mark_paid",
                    old_value={"status": old_status},
                    new_value={"status": "paid", "paid_by": paid_by_user_id},
                    changed_by=paid_by_user_id,
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    metadata={
                        "request_id": payout.id,
                        "agent_id": payout.agent_id,
                        "amount": float(payout.amount),
                        "currency": payout.currency,
                        "payment_reference": payment_reference,
                        "payment_method": payout.payment_method,
                        "notes": notes
                    }
                )

                AuditService.security(
                    event_type="payout_completed",
                    severity=AuditSeverity.INFO,
                    description=f"Payout {payout.request_ref} completed for {payout.amount} {payout.currency}",
                    user_id=payout.agent_id,
                    ip_address=request.remote_addr if request else None,
                    metadata={
                        "request_id": payout.id,
                        "amount": float(payout.amount),
                        "currency": payout.currency,
                        "payment_reference": payment_reference,
                        "paid_by": paid_by_user_id
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to audit payment: {e}")

            current_app.logger.info(
                f"Payout request {payout.request_ref} marked as paid by user {paid_by_user_id}"
            )

            return True

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error marking payout as paid: {e}")
            raise WalletError(f"Failed to mark payout as paid: {str(e)}")

    def get_agent_payout_summary(self, agent_id: int) -> Dict[str, Any]:
        """
        Get payout summary for an agent.

        Args:
            agent_id: User ID of the agent

        Returns:
            Dict with payout statistics
        """
        try:
            from sqlalchemy import func

            # Get totals by status
            results = db.session.query(
                PayoutRequest.status,
                func.sum(PayoutRequest.amount).label('total'),
                func.count(PayoutRequest.id).label('count')
            ).filter(
                PayoutRequest.agent_id == agent_id
            ).group_by(
                PayoutRequest.status
            ).all()

            summary = {
                "agent_id": agent_id,
                "pending_total": Decimal("0"),
                "approved_total": Decimal("0"),
                "paid_total": Decimal("0"),
                "rejected_total": Decimal("0"),
                "pending_count": 0,
                "approved_count": 0,
                "paid_count": 0,
                "rejected_count": 0,
                "total_requested": Decimal("0"),
                "total_requests": 0
            }

            for row in results:
                status = row.status
                total = row.total or Decimal("0")
                count = row.count or 0

                if status == 'pending':
                    summary["pending_total"] = total
                    summary["pending_count"] = count
                elif status == 'approved':
                    summary["approved_total"] = total
                    summary["approved_count"] = count
                elif status == 'paid':
                    summary["paid_total"] = total
                    summary["paid_count"] = count
                elif status == 'rejected':
                    summary["rejected_total"] = total
                    summary["rejected_count"] = count

                summary["total_requested"] += total
                summary["total_requests"] += count

            # Convert to strings for JSON serialization
            summary["pending_total"] = str(summary["pending_total"])
            summary["approved_total"] = str(summary["approved_total"])
            summary["paid_total"] = str(summary["paid_total"])
            summary["rejected_total"] = str(summary["rejected_total"])
            summary["total_requested"] = str(summary["total_requested"])

            return summary

        except Exception as e:
            current_app.logger.error(f"Error getting payout summary for {agent_id}: {e}")
            return {
                "agent_id": agent_id,
                "error": str(e)
            }