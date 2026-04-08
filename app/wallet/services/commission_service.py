# app/wallet/services/commission_service.py - CORRECTED VERSION

"""
Agent commission tracking - Database backed with full audit trails.

This replaces the in-memory agent_tracker.py with proper persistence,
audit logging, and transaction safety.
"""

from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import func, and_
from sqlalchemy.exc import SQLAlchemyError
from flask import current_app, request

from app.extensions import db
from app.wallet.models import AgentCommission
from app.wallet.exceptions import WalletError
from app.audit.comprehensive_audit import AuditService, TransactionType, AuditSeverity


class CommissionService:
    """
    Service for managing agent commissions with full audit trails.

    Features:
    - Database persistence (no more in-memory)
    - Complete audit trail for all commission events
    - Transaction safety with rollback support
    - Idempotency via commission_ref
    - Status tracking (pending, paid, cancelled)
    - Integration with wallet for payouts
    """

    def __init__(self):
        pass

    def record_commission(
            self,
            agent_id: int,
            amount: Decimal,
            currency: str,
            source_type: str,
            source_id: str,
            recipient_id: Optional[int] = None,
            metadata: Optional[Dict] = None,
            idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record a commission earned by an agent with full audit trail.

        Args:
            agent_id: User ID of the agent
            amount: Commission amount
            currency: Currency code (must match wallet currency)
            source_type: peer_transfer, withdrawal, deposit, etc.
            source_id: Reference to the source transaction
            recipient_id: User ID who received the service (for peer transfers)
            metadata: Additional data
            idempotency_key: Unique key to prevent duplicate recording

        Returns:
            Dict with commission record

        Raises:
            DuplicateTransactionError: If idempotency_key already used
            ValueError: If amount is invalid
        """
        from flask import request
        from app.wallet.exceptions import DuplicateTransactionError

        # Validate
        if amount <= Decimal("0"):
            raise ValueError("Commission amount must be greater than zero")

        if not agent_id:
            raise ValueError("Agent ID is required")

        if not source_type or not source_id:
            raise ValueError("Source type and ID are required")

        # Generate commission reference
        import uuid
        commission_ref = idempotency_key or f"COM-{uuid.uuid4().hex[:12].upper()}"

        # Check for duplicate by reference
        existing = AgentCommission.query.filter_by(commission_ref=commission_ref).first()
        if existing:
            raise DuplicateTransactionError(commission_ref, str(existing.id))

        # Get current balance snapshot (for audit)
        from app.wallet.services.wallet_service import WalletService
        wallet_service = WalletService()
        try:
            balance_before = wallet_service.get_balance(agent_id)
            current_balance = Decimal(balance_before.get('balance_home', '0'))
        except Exception as e:
            current_app.logger.warning(f"Could not get balance for audit: {e}")
            current_balance = Decimal("0")

        # Create audit record BEFORE database insert
        audit_id = f"AUD-{uuid.uuid4().hex[:12].upper()}"
        try:
            AuditService.financial(
                transaction_id=commission_ref,
                transaction_type=TransactionType.COMMISSION,
                amount=amount,
                currency=currency,
                status="earned",
                to_user_id=agent_id,
                from_user_id=recipient_id,
                to_balance_before=float(current_balance),
                payment_method=source_type,
                external_reference=source_id,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request else None,
                metadata={
                    "audit_id": audit_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "recipient_id": recipient_id,
                    "client_metadata": metadata or {},
                }
            )
        except Exception as e:
            current_app.logger.error(f"Failed to create audit record for commission: {e}")
            # Continue - don't block commission recording

        # Create database record
        try:
            commission = AgentCommission(
                commission_ref=commission_ref,
                agent_id=agent_id,
                amount=amount,
                currency=currency,
                source_type=source_type,
                source_id=source_id,
                recipient_id=recipient_id,
                status="pending",
                metadata=metadata or {},
                created_at=datetime.utcnow()
            )

            db.session.add(commission)
            db.session.flush()  # Get ID without committing

            # Update audit with commission ID
            try:
                AuditService.financial(
                    transaction_id=commission_ref,
                    transaction_type=TransactionType.COMMISSION,
                    amount=amount,
                    currency=currency,
                    status="earned",
                    to_user_id=agent_id,
                    from_user_id=recipient_id,
                    payment_method=source_type,
                    external_reference=source_id,
                    metadata={
                        "audit_id": audit_id,
                        "commission_id": commission.id,
                        "commission_ref": commission_ref,
                        "source_type": source_type,
                        "source_id": source_id,
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to update audit with commission ID: {e}")

            db.session.commit()

            current_app.logger.info(
                f"Commission recorded: {commission_ref} - agent={agent_id}, "
                f"amount={amount} {currency}, source={source_type}/{source_id}"
            )

            return {
                "id": commission.id,
                "commission_ref": commission.commission_ref,
                "agent_id": commission.agent_id,
                "amount": str(commission.amount),
                "currency": commission.currency,
                "source_type": commission.source_type,
                "source_id": commission.source_id,
                "recipient_id": commission.recipient_id,
                "status": commission.status,
                "metadata": commission.metadata,
                "created_at": commission.created_at.isoformat(),
                "audit_id": audit_id
            }

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error recording commission: {e}")
            raise WalletError(f"Failed to record commission: {str(e)}")

    def get_agent_total(
            self,
            agent_id: int,
            include_pending: bool = True,
            currency: Optional[str] = None
    ) -> Decimal:
        """
        Get total commissions earned by an agent.

        Args:
            agent_id: User ID of the agent
            include_pending: Include pending commissions in total
            currency: Optional filter by currency

        Returns:
            Total amount as Decimal
        """
        try:
            query = db.session.query(func.sum(AgentCommission.amount))

            # Filter by agent
            query = query.filter(AgentCommission.agent_id == agent_id)

            # Filter by status
            if not include_pending:
                query = query.filter(AgentCommission.status == 'paid')
            else:
                query = query.filter(AgentCommission.status.in_(['pending', 'paid']))

            # Filter by currency
            if currency:
                query = query.filter(AgentCommission.currency == currency.upper())

            total = query.scalar() or Decimal("0")
            return Decimal(str(total))

        except Exception as e:
            current_app.logger.error(f"Error getting agent total for {agent_id}: {e}")
            return Decimal("0")

    def get_agent_commissions(
            self,
            agent_id: int,
            status: Optional[str] = None,
            currency: Optional[str] = None,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            limit: int = 100,
            offset: int = 0
    ) -> List[Dict]:
        """
        Get list of commissions for an agent with filters.

        Args:
            agent_id: User ID of the agent
            status: Filter by status (pending, paid, cancelled)
            currency: Filter by currency
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum records to return
            offset: Pagination offset

        Returns:
            List of commission records as dicts
        """
        try:
            query = AgentCommission.query.filter_by(agent_id=agent_id)

            if status:
                query = query.filter_by(status=status)

            if currency:
                query = query.filter_by(currency=currency.upper())

            if start_date:
                query = query.filter(AgentCommission.created_at >= start_date)

            if end_date:
                query = query.filter(AgentCommission.created_at <= end_date)

            commissions = query.order_by(
                AgentCommission.created_at.desc()
            ).offset(offset).limit(limit).all()

            return [
                {
                    "id": c.id,
                    "commission_ref": c.commission_ref,
                    "agent_id": c.agent_id,
                    "amount": str(c.amount),
                    "currency": c.currency,
                    "source_type": c.source_type,
                    "source_id": c.source_id,
                    "recipient_id": c.recipient_id,
                    "status": c.status,
                    "paid_at": c.paid_at.isoformat() if c.paid_at else None,
                    "paid_by": c.paid_by,
                    "metadata": c.metadata,
                    "created_at": c.created_at.isoformat()
                }
                for c in commissions
            ]

        except Exception as e:
            current_app.logger.error(f"Error getting agent commissions for {agent_id}: {e}")
            return []

    def get_pending_total(self, agent_id: int, currency: Optional[str] = None) -> Decimal:
        """
        Get total pending (unpaid) commissions for an agent.

        Args:
            agent_id: User ID of the agent
            currency: Optional filter by currency

        Returns:
            Total pending amount as Decimal
        """
        return self.get_agent_total(agent_id, include_pending=True, currency=currency) - \
            self.get_agent_total(agent_id, include_pending=False, currency=currency)

    def mark_as_paid(
            self,
            commission_id: int,
            paid_by_user_id: int,
            notes: Optional[str] = None
    ) -> bool:
        """
        Mark a commission as paid.

        Args:
            commission_id: ID of the commission record
            paid_by_user_id: Admin user ID who processed payment
            notes: Optional notes about the payment

        Returns:
            True if successful

        Raises:
            WalletError: If commission not found or already paid
        """
        from flask import request

        try:
            commission = AgentCommission.query.get(commission_id)

            if not commission:
                raise WalletError(f"Commission {commission_id} not found")

            if commission.status == 'paid':
                raise WalletError(f"Commission {commission_id} already paid")

            # Record BEFORE state for audit
            old_status = commission.status

            # Update commission
            commission.status = 'paid'
            commission.paid_at = datetime.utcnow()
            commission.paid_by = paid_by_user_id
            if notes:
                commission.metadata = commission.metadata or {}
                commission.metadata['payment_notes'] = notes

            db.session.commit()

            # Audit the payment
            try:
                AuditService.financial(
                    transaction_id=commission.commission_ref,
                    transaction_type=TransactionType.PAYOUT,
                    amount=commission.amount,
                    currency=commission.currency,
                    status="paid",
                    to_user_id=commission.agent_id,
                    from_user_id=paid_by_user_id,
                    external_reference=str(commission.id),
                    ip_address=request.remote_addr if request else None,
                    metadata={
                        "commission_id": commission.id,
                        "commission_ref": commission.commission_ref,
                        "old_status": old_status,
                        "notes": notes,
                        "paid_by": paid_by_user_id
                    }
                )

                AuditService.security(
                    event_type="commission_paid",
                    severity=AuditSeverity.INFO,
                    description=f"Commission {commission.commission_ref} paid to agent {commission.agent_id}",
                    user_id=commission.agent_id,
                    metadata={
                        "commission_id": commission.id,
                        "amount": float(commission.amount),
                        "currency": commission.currency,
                        "paid_by": paid_by_user_id
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to audit commission payment: {e}")

            current_app.logger.info(
                f"Commission {commission.commission_ref} marked as paid by user {paid_by_user_id}"
            )

            return True

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error marking commission as paid: {e}")
            raise WalletError(f"Failed to mark commission as paid: {str(e)}")

    def mark_as_cancelled(
            self,
            commission_id: int,
            cancelled_by_user_id: int,
            reason: str
    ) -> bool:
        """
        Cancel a pending commission.

        Args:
            commission_id: ID of the commission record
            cancelled_by_user_id: Admin user ID who cancelled
            reason: Reason for cancellation

        Returns:
            True if successful
        """
        from flask import request

        try:
            commission = AgentCommission.query.get(commission_id)

            if not commission:
                raise WalletError(f"Commission {commission_id} not found")

            if commission.status != 'pending':
                raise WalletError(f"Cannot cancel commission with status: {commission.status}")

            old_status = commission.status

            # Update commission
            commission.status = 'cancelled'
            commission.metadata = commission.metadata or {}
            commission.metadata['cancelled_at'] = datetime.utcnow().isoformat()
            commission.metadata['cancelled_by'] = cancelled_by_user_id
            commission.metadata['cancellation_reason'] = reason

            db.session.commit()

            # Audit the cancellation
            try:
                AuditService.security(
                    event_type="commission_cancelled",
                    severity=AuditSeverity.WARNING,
                    description=f"Commission {commission.commission_ref} cancelled",
                    user_id=commission.agent_id,
                    ip_address=request.remote_addr if request else None,
                    metadata={
                        "commission_id": commission.id,
                        "commission_ref": commission.commission_ref,
                        "amount": float(commission.amount),
                        "currency": commission.currency,
                        "reason": reason,
                        "cancelled_by": cancelled_by_user_id,
                        "old_status": old_status
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to audit commission cancellation: {e}")

            return True

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error cancelling commission: {e}")
            raise WalletError(f"Failed to cancel commission: {str(e)}")

    def get_commission_summary(self, agent_id: int) -> Dict[str, Any]:
        """
        Get summary statistics for an agent's commissions.

        Args:
            agent_id: User ID of the agent

        Returns:
            Dict with summary statistics
        """
        try:
            # Get totals by currency
            results = db.session.query(
                AgentCommission.currency,
                func.sum(AgentCommission.amount).label('total'),
                func.sum(AgentCommission.amount).filter(AgentCommission.status == 'pending').label('pending'),
                func.sum(AgentCommission.amount).filter(AgentCommission.status == 'paid').label('paid'),
                func.count(AgentCommission.id).label('count')
            ).filter(
                AgentCommission.agent_id == agent_id
            ).group_by(
                AgentCommission.currency
            ).all()

            summary = {
                "agent_id": agent_id,
                "currencies": {},
                "total_all": Decimal("0"),
                "pending_all": Decimal("0"),
                "paid_all": Decimal("0"),
                "total_count": 0
            }

            for row in results:
                currency_data = {
                    "total": str(row.total or Decimal("0")),
                    "pending": str(row.pending or Decimal("0")),
                    "paid": str(row.paid or Decimal("0")),
                    "count": row.count or 0
                }
                summary["currencies"][row.currency] = currency_data

                summary["total_all"] += (row.total or Decimal("0"))
                summary["pending_all"] += (row.pending or Decimal("0"))
                summary["paid_all"] += (row.paid or Decimal("0"))
                summary["total_count"] += (row.count or 0)

            summary["total_all"] = str(summary["total_all"])
            summary["pending_all"] = str(summary["pending_all"])
            summary["paid_all"] = str(summary["paid_all"])

            return summary

        except Exception as e:
            current_app.logger.error(f"Error getting commission summary for {agent_id}: {e}")
            return {
                "agent_id": agent_id,
                "currencies": {},
                "total_all": "0",
                "pending_all": "0",
                "paid_all": "0",
                "total_count": 0,
                "error": str(e)
            }

    def bulk_mark_as_paid(
            self,
            commission_ids: List[int],
            paid_by_user_id: int,
            notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mark multiple commissions as paid in bulk.

        Args:
            commission_ids: List of commission IDs
            paid_by_user_id: Admin user ID who processed payment
            notes: Optional notes about the payment

        Returns:
            Dict with success/failure counts
        """
        from flask import request

        result = {
            "successful": [],
            "failed": [],
            "total": len(commission_ids),
            "success_count": 0,
            "failed_count": 0
        }

        for commission_id in commission_ids:
            try:
                self.mark_as_paid(commission_id, paid_by_user_id, notes)
                result["successful"].append(commission_id)
                result["success_count"] += 1
            except Exception as e:
                result["failed"].append({
                    "id": commission_id,
                    "error": str(e)
                })
                result["failed_count"] += 1

        # Audit bulk operation
        try:
            AuditService.security(
                event_type="bulk_commission_payment",
                severity=AuditSeverity.INFO,
                description=f"Bulk payment of {result['success_count']} commissions",
                user_id=paid_by_user_id,
                ip_address=request.remote_addr if request else None,
                metadata={
                    "total": result["total"],
                    "successful": result["success_count"],
                    "failed": result["failed_count"],
                    "commission_ids": commission_ids,
                    "notes": notes
                }
            )
        except Exception as e:
            current_app.logger.error(f"Failed to audit bulk payment: {e}")

        return result

    def get_unpaid_commissions_by_agent(
            self,
            agent_id: int,
            currency: Optional[str] = None
    ) -> List[Dict]:
        """
        Get all unpaid commissions for an agent.
        Useful for payout calculations.

        Args:
            agent_id: User ID of the agent
            currency: Optional filter by currency

        Returns:
            List of unpaid commission records
        """
        return self.get_agent_commissions(
            agent_id=agent_id,
            status='pending',
            currency=currency,
            limit=1000  # No limit for payouts
        )
