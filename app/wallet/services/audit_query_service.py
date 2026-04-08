"""
app/wallet/services/audit_query_service.py
Service for querying audit logs with filters and pagination.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from decimal import Decimal
from flask import current_app
from sqlalchemy import func, or_, and_

from app.extensions import db
from app.audit.comprehensive_audit import (
    FinancialAuditLog,
    APIAuditLog,
    SecurityEventLog,
    DataAccessLog,
    AuditSeverity,
    TransactionType,
    APICallStatus
)
from app.wallet.exceptions import WalletError


class AuditQueryService:
    """
    Service for querying audit logs.

    Features:
    - Query financial transactions with filters
    - Query security events with severity filtering
    - Query API call logs
    - Query data access logs (GDPR)
    - AML flagged transaction review
    """

    def __init__(self):
        pass

    # ========================================================================
    # FINANCIAL AUDIT QUERIES
    # ========================================================================

    def query_financial_logs(
            self,
            user_id: Optional[int] = None,
            transaction_type: Optional[str] = None,
            status: Optional[str] = None,
            aml_flagged: Optional[bool] = None,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            min_amount: Optional[Decimal] = None,
            max_amount: Optional[Decimal] = None,
            currency: Optional[str] = None,
            payment_provider: Optional[str] = None,
            page: int = 1,
            per_page: int = 50,
            sort_by: str = "created_at",
            sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """
        Query financial audit logs with filters.
        """
        try:
            query = FinancialAuditLog.query

            # Apply filters
            if user_id:
                query = query.filter(
                    or_(
                        FinancialAuditLog.from_user_id == user_id,
                        FinancialAuditLog.to_user_id == user_id
                    )
                )

            if transaction_type:
                query = query.filter(FinancialAuditLog.transaction_type == transaction_type)

            if status:
                query = query.filter(FinancialAuditLog.status == status)

            if aml_flagged is not None:
                query = query.filter(FinancialAuditLog.aml_flagged == aml_flagged)

            if start_date:
                query = query.filter(FinancialAuditLog.created_at >= start_date)

            if end_date:
                query = query.filter(FinancialAuditLog.created_at <= end_date)

            if min_amount:
                query = query.filter(FinancialAuditLog.amount >= min_amount)

            if max_amount:
                query = query.filter(FinancialAuditLog.amount <= max_amount)

            if currency:
                query = query.filter(FinancialAuditLog.currency == currency.upper())

            if payment_provider:
                query = query.filter(FinancialAuditLog.payment_provider == payment_provider)

            # Get total count
            total = query.count()

            # Apply sorting
            if sort_by == "amount":
                order_col = FinancialAuditLog.amount
            else:
                order_col = FinancialAuditLog.created_at

            if sort_order == "asc":
                query = query.order_by(order_col.asc())
            else:
                query = query.order_by(order_col.desc())

            # Paginate
            offset = (page - 1) * per_page
            logs = query.offset(offset).limit(per_page).all()

            # Get summary statistics
            summary = self._get_financial_summary(query)

            return {
                "transactions": [
                    {
                        "id": log.id,
                        "transaction_id": log.transaction_id,
                        "transaction_type": self._enum_value(log.transaction_type),
                        "amount": str(log.amount),
                        "currency": log.currency,
                        "status": log.status,
                        "from_user_id": log.from_user_id,
                        "to_user_id": log.to_user_id,
                        "payment_method": log.payment_method,
                        "payment_provider": log.payment_provider,
                        "external_reference": log.external_reference,
                        "risk_score": float(log.risk_score) if log.risk_score else None,
                        "aml_flagged": log.aml_flagged,
                        "requires_review": log.requires_review,
                        "ip_address": log.ip_address,
                        "created_at": log.created_at.isoformat(),
                        "metadata": log.extra_data,
                    }
                    for log in logs
                ],
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page if per_page > 0 else 1,
                "summary": summary
            }

        except Exception as e:
            current_app.logger.error(f"Error querying financial logs: {e}")
            raise WalletError(f"Failed to query financial logs: {str(e)}")

    def _get_financial_summary(self, query) -> Dict[str, Any]:
        """Get summary statistics for financial logs."""
        try:
            # Get total volume
            results = query.all()
            if not results:
                return {}

            total_volume = sum(float(r.amount) for r in results)

            # Volume by type
            volume_by_type = {}
            for r in results:
                tx_type = self._enum_value(r.transaction_type)
                volume_by_type[tx_type] = volume_by_type.get(tx_type, 0) + float(r.amount)

            return {
                "total_volume": f"{total_volume:.2f}",
                "volume_by_type": [
                    {"type": k, "total": f"{v:.2f}"}
                    for k, v in volume_by_type.items()
                ],
                "aml_flagged_count": sum(1 for r in results if r.aml_flagged),
                "requires_review_count": sum(1 for r in results if r.requires_review)
            }
        except Exception as e:
            current_app.logger.error(f"Error getting financial summary: {e}")
            return {}

    # ========================================================================
    # SECURITY EVENT QUERIES
    # ========================================================================

    def query_security_events(
            self,
            user_id: Optional[int] = None,
            event_type: Optional[str] = None,
            severity: Optional[str] = None,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            page: int = 1,
            per_page: int = 50
    ) -> Dict[str, Any]:
        """
        Query security event logs.
        """
        try:
            query = SecurityEventLog.query

            if user_id:
                query = query.filter(SecurityEventLog.user_id == user_id)

            if event_type:
                query = query.filter(SecurityEventLog.event_type == event_type)

            if severity:
                query = query.filter(SecurityEventLog.severity == severity)

            if start_date:
                query = query.filter(SecurityEventLog.created_at >= start_date)

            if end_date:
                query = query.filter(SecurityEventLog.created_at <= end_date)

            total = query.count()
            offset = (page - 1) * per_page
            events = query.order_by(SecurityEventLog.created_at.desc()).offset(offset).limit(per_page).all()

            # Get severity breakdown
            severity_counts = {}
            for e in events:
                sev = self._enum_value(e.severity)
                severity_counts[sev] = severity_counts.get(sev, 0) + 1

            return {
                "events": [
                    {
                        "id": e.id,
                        "event_type": e.event_type,
                        "severity": self._enum_value(e.severity),
                        "description": e.description,
                        "user_id": e.user_id,
                        "ip_address": e.ip_address,
                        "action_taken": e.action_taken,
                        "handled_by": e.handled_by,
                        "handled_at": e.handled_at.isoformat() if e.handled_at else None,
                        "created_at": e.created_at.isoformat(),
                        "metadata": e.extra_data,
                    }
                    for e in events
                ],
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page if per_page > 0 else 1,
                "severity_breakdown": [
                    {"severity": k, "count": v}
                    for k, v in severity_counts.items()
                ]
            }

        except Exception as e:
            current_app.logger.error(f"Error querying security events: {e}")
            raise WalletError(f"Failed to query security events: {str(e)}")

    # ========================================================================
    # API LOG QUERIES
    # ========================================================================

    def query_api_logs(
            self,
            service_name: Optional[str] = None,
            status: Optional[str] = None,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            page: int = 1,
            per_page: int = 50
    ) -> Dict[str, Any]:
        """
        Query API call logs.
        """
        try:
            query = APIAuditLog.query

            if service_name:
                query = query.filter(APIAuditLog.service_name == service_name)

            if status:
                query = query.filter(APIAuditLog.status == status)

            if start_date:
                query = query.filter(APIAuditLog.created_at >= start_date)

            if end_date:
                query = query.filter(APIAuditLog.created_at <= end_date)

            total = query.count()
            offset = (page - 1) * per_page
            logs = query.order_by(APIAuditLog.created_at.desc()).offset(offset).limit(per_page).all()

            return {
                "api_calls": [
                    {
                        "id": l.id,
                        "service_name": l.service_name,
                        "endpoint": l.endpoint,
                        "method": l.method,
                        "status": self._enum_value(l.status),
                        "response_status": l.response_status,
                        "response_time_ms": l.response_time_ms,
                        "error_message": l.error_message,
                        "retry_count": l.retry_count,
                        "initiated_by": l.initiated_by,
                        "created_at": l.created_at.isoformat(),
                    }
                    for l in logs
                ],
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page if per_page > 0 else 1
            }

        except Exception as e:
            current_app.logger.error(f"Error querying API logs: {e}")
            raise WalletError(f"Failed to query API logs: {str(e)}")

    # ========================================================================
    # DATA ACCESS LOG QUERIES (GDPR)
    # ========================================================================

    def query_data_access_logs(
            self,
            user_id: Optional[int] = None,
            accessed_by: Optional[int] = None,
            data_category: Optional[str] = None,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            page: int = 1,
            per_page: int = 50
    ) -> Dict[str, Any]:
        """
        Query data access logs for GDPR compliance.
        """
        try:
            query = DataAccessLog.query

            if user_id:
                query = query.filter(DataAccessLog.subject_user_id == user_id)

            if accessed_by:
                query = query.filter(DataAccessLog.accessed_by == accessed_by)

            if data_category:
                query = query.filter(DataAccessLog.data_category == data_category)

            if start_date:
                query = query.filter(DataAccessLog.created_at >= start_date)

            if end_date:
                query = query.filter(DataAccessLog.created_at <= end_date)

            total = query.count()
            offset = (page - 1) * per_page
            logs = query.order_by(DataAccessLog.created_at.desc()).offset(offset).limit(per_page).all()

            return {
                "access_logs": [
                    {
                        "id": l.id,
                        "accessed_by": l.accessed_by,
                        "subject_user_id": l.subject_user_id,
                        "access_type": self._enum_value(l.access_type),
                        "data_category": l.data_category,
                        "resource_type": l.resource_type,
                        "resource_id": l.resource_id,
                        "fields_accessed": l.fields_accessed,
                        "purpose": l.purpose,
                        "legal_basis": l.legal_basis,
                        "ip_address": l.ip_address,
                        "created_at": l.created_at.isoformat(),
                    }
                    for l in logs
                ],
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page if per_page > 0 else 1
            }

        except Exception as e:
            current_app.logger.error(f"Error querying data access logs: {e}")
            raise WalletError(f"Failed to query data access logs: {str(e)}")

    # ========================================================================
    # AML REVIEW FUNCTIONS
    # ========================================================================

    def get_aml_flagged_transactions(
            self,
            requires_review: bool = True,
            page: int = 1,
            per_page: int = 50
    ) -> Dict[str, Any]:
        """
        Get AML flagged transactions that need review.
        """
        try:
            query = FinancialAuditLog.query.filter(
                FinancialAuditLog.aml_flagged == True
            )

            if requires_review:
                query = query.filter(FinancialAuditLog.requires_review == True)

            total = query.count()
            offset = (page - 1) * per_page
            transactions = query.order_by(FinancialAuditLog.created_at.desc()).offset(offset).limit(per_page).all()

            return {
                "transactions": [
                    {
                        "id": t.id,
                        "transaction_id": t.transaction_id,
                        "transaction_type": self._enum_value(t.transaction_type),
                        "amount": str(t.amount),
                        "currency": t.currency,
                        "risk_score": float(t.risk_score) if t.risk_score else None,
                        "user_id": t.from_user_id or t.to_user_id,
                        "created_at": t.created_at.isoformat(),
                        "requires_review": t.requires_review,
                        "reviewed_by": t.reviewed_by,
                        "reviewed_at": t.reviewed_at.isoformat() if t.reviewed_at else None,
                        "metadata": t.extra_data,
                    }
                    for t in transactions
                ],
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page if per_page > 0 else 1
            }

        except Exception as e:
            current_app.logger.error(f"Error getting AML flagged transactions: {e}")
            raise WalletError(f"Failed to get AML flagged transactions: {str(e)}")

    def review_aml_flag(
            self,
            transaction_id: int,
            reviewer_id: int,
            approved: bool,
            notes: Optional[str] = None
    ) -> bool:
        """
        Review and resolve an AML flagged transaction.
        """
        from flask import request

        try:
            transaction = FinancialAuditLog.query.get(transaction_id)
            if not transaction:
                raise ValueError(f"Transaction {transaction_id} not found")

            transaction.requires_review = False
            transaction.reviewed_by = reviewer_id
            transaction.reviewed_at = datetime.utcnow()

            if notes:
                transaction.extra_data = transaction.extra_data or {}
                transaction.extra_data['review_notes'] = notes
                transaction.extra_data['review_approved'] = approved
                transaction.extra_data['reviewed_by'] = reviewer_id
                transaction.extra_data['reviewed_at'] = datetime.utcnow().isoformat()

            db.session.commit()

            # Log the review action to security events
            try:
                from app.audit.comprehensive_audit import AuditService, AuditSeverity
                AuditService.security(
                    event_type="aml_review_completed",
                    severity=AuditSeverity.INFO,
                    description=f"AML flag reviewed by user {reviewer_id}. Approved: {approved}",
                    user_id=transaction.from_user_id or transaction.to_user_id,
                    ip_address=request.remote_addr if request else None,
                    metadata={
                        "transaction_id": transaction.transaction_id,
                        "reviewer_id": reviewer_id,
                        "approved": approved,
                        "notes": notes
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to log AML review: {e}")

            return True

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error reviewing AML flag: {e}")
            raise WalletError(f"Failed to review AML flag: {str(e)}")

    # ========================================================================
    # EXPORT FUNCTIONS
    # ========================================================================

    def export_audit_data(
            self,
            log_type: str,
            format: str = "json",
            **filters
    ) -> str:
        """
        Export audit data to JSON or CSV format.
        """
        import json
        import csv
        from io import StringIO

        per_page = 10000  # Max export limit

        if log_type == "financial":
            result = self.query_financial_logs(**filters, page=1, per_page=per_page)
            data = result.get("transactions", [])
        elif log_type == "security":
            result = self.query_security_events(**filters, page=1, per_page=per_page)
            data = result.get("events", [])
        elif log_type == "api":
            result = self.query_api_logs(**filters, page=1, per_page=per_page)
            data = result.get("api_calls", [])
        elif log_type == "data_access":
            result = self.query_data_access_logs(**filters, page=1, per_page=per_page)
            data = result.get("access_logs", [])
        elif log_type == "aml":
            result = self.get_aml_flagged_transactions(**filters, page=1, per_page=per_page)
            data = result.get("transactions", [])
        else:
            raise ValueError(f"Unknown log type: {log_type}")

        if format == "json":
            return json.dumps(data, indent=2, default=str)
        elif format == "csv":
            if not data:
                return ""
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _enum_value(self, enum_obj) -> str:
        """Safely get enum value."""
        if hasattr(enum_obj, 'value'):
            return enum_obj.value
        return str(enum_obj) if enum_obj else None
