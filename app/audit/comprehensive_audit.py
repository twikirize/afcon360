# app/audit/comprehensive_audit.py
"""
Comprehensive Audit System for AFCON360

Meets requirements for:
- State regulatory compliance (Uganda, Kenya, Tanzania financial regulations)
- Banking system integration (SWIFT, local payment processors)
- KYC/AML compliance (FATF recommendations)
- PCI-DSS (if handling card data)
- GDPR/data protection
- Financial transaction auditing
- Third-party API integration tracking

Architecture:
1. AuditLog - General user/system actions
2. ComplianceAuditLog - Regulatory decisions (KYC, AML, transaction limits)
3. FinancialAuditLog - All money movements (NEW)
4. APIAuditLog - Third-party integrations (NEW)
5. DataAccessLog - GDPR/privacy compliance (NEW)
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from decimal import Decimal
from enum import Enum
import uuid
from sqlalchemy import Column, BigInteger, String,Integer, DateTime, JSON, Numeric, Enum as SQLEnum, Index, Boolean, Text
from sqlalchemy.orm import Session
from app.extensions import db
from app.models.base import BaseModel
import logging
from typing import Any
import json

logger = logging.getLogger(__name__)


# ============================================================================
# Enums for Audit Types
# ============================================================================

class AuditSeverity(str, Enum):
    """Audit event severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SECURITY = "security"


class TransactionType(str, Enum):
    """Financial transaction types"""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    REFUND = "refund"
    FEE = "fee"
    REVERSAL = "reversal"
    CURRENCY_EXCHANGE = "currency_exchange"
    COMMISSION = "commission"
    PAYOUT = "payout"
    EXCHANGE = "exchange"


class APICallStatus(str, Enum):
    """Third-party API call status"""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


class DataAccessType(str, Enum):
    """GDPR data access types"""
    READ = "read"
    EXPORT = "export"
    DELETE = "delete"
    MODIFY = "modify"


# ============================================================================
# 1. FINANCIAL AUDIT LOG (Critical for Banking Integration)
# ============================================================================

class FinancialAuditLog(BaseModel):
    """
    Immutable audit log for ALL financial transactions.

    Required for:
    - Banking reconciliation
    - Financial reporting to regulators
    - Fraud investigation
    - Tax compliance
    - Dispute resolution

    Retention: PERMANENT (never delete)
    """
    __tablename__ = "financial_audit_logs"


    # Transaction identification
    transaction_id = Column(String(128), nullable=False, unique=True, index=True)
    transaction_type = Column(SQLEnum(TransactionType), nullable=False)

    # Parties involved
    from_user_id = Column(BigInteger, index=True)  # Sender
    to_user_id = Column(BigInteger, index=True)  # Receiver
    organisation_id = Column(BigInteger, index=True)  # If org transaction

    # Financial details
    amount = Column(Numeric(20, 4), nullable=False)  # Exact decimal precision
    currency = Column(String(3), nullable=False, index=True)  # ISO 4217

    # Exchange rate info (if currency conversion)
    exchange_rate = Column(Numeric(20, 8))
    original_amount = Column(Numeric(20, 4))
    original_currency = Column(String(3))

    # Fee tracking
    fee_amount = Column(Numeric(20, 4), default=0)
    fee_currency = Column(String(3))

    # Balance snapshots (for reconciliation)
    from_balance_before = Column(Numeric(20, 4))
    from_balance_after = Column(Numeric(20, 4))
    to_balance_before = Column(Numeric(20, 4))
    to_balance_after = Column(Numeric(20, 4))

    # Transaction status and metadata
    status = Column(String(32), nullable=False, index=True)  # pending, completed, failed, reversed
    payment_method = Column(String(64))  # bank_transfer, mobile_money, card, etc.
    payment_provider = Column(String(64))  # MTN, Airtel, Visa, etc.
    external_reference = Column(String(255))  # Provider's transaction ID

    # Risk and compliance
    risk_score = Column(Numeric(5, 2))  # 0.00 to 100.00
    aml_flagged = Column(Boolean, default=False, index=True)
    requires_review = Column(Boolean, default=False, index=True)
    reviewed_by = Column(BigInteger)
    reviewed_at = Column(DateTime)

    # Contextual information
    ip_address = Column(String(64))
    user_agent = Column(String(512))
    device_fingerprint = Column(String(128))
    geolocation = Column(JSON)  # {country, city, lat, lng}

    # Audit trail
    initiated_by = Column(BigInteger)  # User who initiated
    approved_by = Column(BigInteger)  # For high-value transactions

    # Full transaction context (renamed from 'metadata' to avoid SQLAlchemy reserved word)
    extra_data = Column(JSON)  # Additional context

    completed_at = Column(DateTime)

    # Indexes for common queries
    __table_args__ = (
        Index('idx_fin_user_date', 'from_user_id', 'created_at'),
        Index('idx_fin_org_date', 'organisation_id', 'created_at'),
        Index('idx_fin_status_date', 'status', 'created_at'),
        Index('idx_fin_currency_date', 'currency', 'created_at'),
        Index('idx_fin_aml', 'aml_flagged', 'created_at'),
    )

    @staticmethod
    def log_transaction(
            transaction_id: str,
            transaction_type: TransactionType,
            amount: Decimal,
            currency: str,
            status: str,
            from_user_id: Optional[int] = None,
            to_user_id: Optional[int] = None,
            organisation_id: Optional[int] = None,
            payment_method: Optional[str] = None,
            payment_provider: Optional[str] = None,
            external_reference: Optional[str] = None,
            extra_data: Optional[Dict] = None,
            ip_address: Optional[str] = None,
            **kwargs
    ) -> 'FinancialAuditLog':
        """Create immutable financial audit record"""

        log_entry = FinancialAuditLog(
            transaction_id=transaction_id,
            transaction_type=transaction_type,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            organisation_id=organisation_id,
            amount=amount,
            currency=currency,
            status=status,
            payment_method=payment_method,
            payment_provider=payment_provider,
            external_reference=external_reference,
            extra_data=extra_data or {},
            ip_address=ip_address,
            **kwargs
        )

        db.session.add(log_entry)
        db.session.commit()

        logger.info(f"Financial audit: {transaction_type} {amount} {currency} - {transaction_id}")
        return log_entry


# ============================================================================
# 2. API AUDIT LOG (Third-Party Integration Tracking)
# ============================================================================

class APIAuditLog(BaseModel):
    """
    Track all third-party API calls for debugging and compliance.

    Required for:
    - Payment provider reconciliation
    - SLA monitoring
    - Security incident investigation
    - Billing verification

    Retention: 2 years minimum
    """
    __tablename__ = "api_audit_logs"


    # API identification
    service_name = Column(String(64), nullable=False, index=True)  # "flutterwave", "mtn_momo"
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)  # GET, POST, etc.

    # Request tracking
    request_id = Column(String(128), unique=True, index=True)
    correlation_id = Column(String(128), index=True)  # Link to transaction

    # Request details
    request_payload = Column(JSON)  # Sanitized (no secrets)
    request_headers = Column(JSON)  # Sanitized

    # Response details
    response_status = Column(Integer)
    response_body = Column(JSON)
    response_time_ms = Column(Integer)  # Latency tracking

    # Status
    status = Column(SQLEnum(APICallStatus), nullable=False, index=True)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # Security
    api_key_used = Column(String(64))  # Identifier only, not the actual key
    ip_address = Column(String(64))

    # Audit
    initiated_by = Column(BigInteger)  # User or system

    __table_args__ = (
        Index('idx_api_service_date', 'service_name', 'created_at'),
        Index('idx_api_status_date', 'status', 'created_at'),
    )

    @staticmethod
    def log_api_call(
            service_name: str,
            endpoint: str,
            method: str,
            request_id: str,
            status: APICallStatus,
            response_status: Optional[int] = None,
            response_time_ms: Optional[int] = None,
            correlation_id: Optional[str] = None,
            error_message: Optional[str] = None,
            **kwargs
    ) -> 'APIAuditLog':
        """Log third-party API call"""

        log_entry = APIAuditLog(
            service_name=service_name,
            endpoint=endpoint,
            method=method,
            request_id=request_id,
            correlation_id=correlation_id,
            status=status,
            response_status=response_status,
            response_time_ms=response_time_ms,
            error_message=error_message,
            **kwargs
        )

        db.session.add(log_entry)
        db.session.commit()

        return log_entry


# ============================================================================
# 3. DATA ACCESS LOG (GDPR/Privacy Compliance)
# ============================================================================

class DataAccessLog(BaseModel):
    """
    Track access to sensitive personal data for GDPR compliance.

    Required for:
    - GDPR Article 15 (Right of access)
    - Data breach notification
    - Privacy impact assessments
    - User data export requests

    Retention: 3 years minimum
    """
    __tablename__ = "data_access_logs"


    # Access details
    accessed_by = Column(BigInteger, nullable=False, index=True)  # Who accessed
    subject_user_id = Column(BigInteger, nullable=False, index=True)  # Whose data

    access_type = Column(SQLEnum(DataAccessType), nullable=False)
    data_category = Column(String(64), nullable=False)  # "kyc_documents", "financial_records"

    # What was accessed
    resource_type = Column(String(64))  # "user_profile", "wallet_transaction"
    resource_id = Column(String(128))
    fields_accessed = Column(JSON)  # List of field names

    # Context
    purpose = Column(String(255))  # "customer_support", "fraud_investigation"
    legal_basis = Column(String(64))  # "consent", "legal_obligation", "legitimate_interest"

    # Audit
    ip_address = Column(String(64))
    user_agent = Column(String(512))

    __table_args__ = (
        Index('idx_data_subject_date', 'subject_user_id', 'created_at'),
        Index('idx_data_accessor_date', 'accessed_by', 'created_at'),
    )

    @staticmethod
    def log_access(
            accessed_by: int,
            subject_user_id: int,
            access_type: DataAccessType,
            data_category: str,
            purpose: str,
            legal_basis: str = "legitimate_interest",
            **kwargs
    ) -> 'DataAccessLog':
        """Log sensitive data access"""

        log_entry = DataAccessLog(
            accessed_by=accessed_by,
            subject_user_id=subject_user_id,
            access_type=access_type,
            data_category=data_category,
            purpose=purpose,
            legal_basis=legal_basis,
            **kwargs
        )

        db.session.add(log_entry)
        db.session.commit()

        return log_entry


# ============================================================================
# 4. SECURITY EVENT LOG (Critical Security Monitoring)
# ============================================================================

class SecurityEventLog(BaseModel):
    """
    Track security-relevant events for incident response.

    Required for:
    - Intrusion detection
    - Fraud prevention
    - Compliance audits (SOC 2, ISO 27001)

    Retention: 7 years
    """
    __tablename__ = "security_event_logs"


    event_type = Column(String(64), nullable=False, index=True)
    severity = Column(SQLEnum(AuditSeverity), nullable=False, index=True)

    user_id = Column(BigInteger, index=True)
    ip_address = Column(String(64), index=True)
    user_agent = Column(String(512))

    # Event details
    description = Column(Text)
    extra_data = Column(JSON)  # Renamed from 'metadata'

    # Response
    action_taken = Column(String(128))  # "account_locked", "ip_blocked"
    handled_by = Column(BigInteger)
    handled_at = Column(DateTime)


    @staticmethod
    def log_event(
            event_type: str,
            severity: AuditSeverity,
            description: str,
            user_id: Optional[int] = None,
            ip_address: Optional[str] = None,
            **kwargs
    ) -> 'SecurityEventLog':
        """Log security event"""
        # Ensure severity is an AuditSeverity enum value
        if isinstance(severity, str):
            # Try to convert string to enum
            try:
                severity = AuditSeverity(severity.lower())
            except ValueError:
                # Default to INFO if invalid
                logger.warning(f"Invalid severity value '{severity}', defaulting to 'info'")
                severity = AuditSeverity.INFO
        elif not isinstance(severity, AuditSeverity):
            # If it's neither string nor enum, default to INFO
            logger.warning(f"Invalid severity type '{type(severity)}', defaulting to 'info'")
            severity = AuditSeverity.INFO

        log_entry = SecurityEventLog(
            event_type=event_type,
            severity=severity,
            description=description,
            user_id=user_id,
            ip_address=ip_address,
            **kwargs
        )

        db.session.add(log_entry)
        db.session.commit()

        # Alert on critical events
        if severity == AuditSeverity.CRITICAL:
            logger.critical(f"SECURITY ALERT: {event_type} - {description}")

        return log_entry


# ============================================================================
# 5. DATA CHANGE LOG (For audit of data modifications)
# ============================================================================

class DataChangeLog(BaseModel):
    """
    Track changes to data entities (wallet creation, freezing, payouts, etc.)

    Retention: 7 years
    """
    __tablename__ = "data_change_logs"

    # ADD THIS LINE - public_id for IDGuard compliance
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(128), nullable=False, index=True)
    operation = Column(String(32), nullable=False)  # create, update, delete, freeze, unfreeze

    old_value = Column(JSON)
    new_value = Column(JSON)

    changed_by = Column(BigInteger, index=True)
    ip_address = Column(String(64))
    user_agent = Column(String(512))

    extra_data = Column(JSON)  # Renamed from 'metadata'

    __table_args__ = (
        Index('idx_dc_entity', 'entity_type', 'entity_id'),
        Index('idx_dc_changed_by', 'changed_by', 'created_at'),
        Index('idx_dc_public_id', 'public_id'),  # ADD THIS INDEX
    )

    @staticmethod
    def log_change(
            entity_type: str,
            entity_id: str,
            operation: str,
            old_value: Any,
            new_value: Any,
            changed_by: int,
            ip_address: Optional[str] = None,
            user_agent: Optional[str] = None,
            extra_data: Optional[Dict] = None
    ) -> 'DataChangeLog':
        """Log a data change event"""

        # Sanitize sensitive data
        sanitized_old = None
        sanitized_new = None

        if old_value:
            if isinstance(old_value, dict):
                sanitized_old = {}
                for key, value in old_value.items():
                    if 'password' in key.lower() or 'secret' in key.lower():
                        sanitized_old[key] = '[REDACTED]'
                    elif 'account_number' in key.lower() and isinstance(value, str) and len(value) > 4:
                        sanitized_old[key] = value[:4] + '****'
                    else:
                        sanitized_old[key] = value
            else:
                sanitized_old = {'value': str(old_value)}

        if new_value:
            if isinstance(new_value, dict):
                sanitized_new = {}
                for key, value in new_value.items():
                    if 'password' in key.lower() or 'secret' in key.lower():
                        sanitized_new[key] = '[REDACTED]'
                    elif 'account_number' in key.lower() and isinstance(value, str) and len(value) > 4:
                        sanitized_new[key] = value[:4] + '****'
                    else:
                        sanitized_new[key] = value
            else:
                sanitized_new = {'value': str(new_value)}

        log_entry = DataChangeLog(
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            operation=operation,
            old_value=sanitized_old,
            new_value=sanitized_new,
            changed_by=changed_by,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data=extra_data or {}
        )

        db.session.add(log_entry)
        db.session.commit()

        return log_entry


# ============================================================================
# 6. AUDIT SERVICE (Unified Interface)
# ============================================================================

class AuditService:
    """
    Unified audit service that routes to appropriate log tables.

    Usage:
        from app.audit.comprehensive_audit import AuditService

        # Financial transaction
        AuditService.financial(
            transaction_id="TXN123",
            transaction_type=TransactionType.WITHDRAWAL,
            amount=Decimal("1000.00"),
            currency="UGX",
            from_user_id=user.id,
            status="completed"
        )

        # Third-party API call
        AuditService.api_call(
            service_name="flutterwave",
            endpoint="/v3/payments",
            method="POST",
            request_id=request_id,
            status=APICallStatus.SUCCESS
        )

        # Sensitive data access
        AuditService.data_access(
            accessed_by=admin.id,
            subject_user_id=user.id,
            access_type=DataAccessType.READ,
            data_category="kyc_documents",
            purpose="compliance_review"
        )

        # Security event
        AuditService.security(
            event_type="brute_force_attempt",
            severity=AuditSeverity.CRITICAL,
            description="10 failed login attempts",
            ip_address=request.remote_addr
        )

        # Data change (wallet freeze, payout request, etc.)
        AuditService.data_change(
            entity_type="wallet",
            entity_id=wallet_id,
            operation="freeze",
            old_value={"status": "active"},
            new_value={"status": "frozen", "reason": reason},
            changed_by=admin.id
        )
    """

    @staticmethod
    def financial(**kwargs) -> FinancialAuditLog:
        """Log financial transaction"""
        # Map 'metadata' parameter to 'extra_data' for compatibility
        if 'metadata' in kwargs:
            kwargs['extra_data'] = kwargs.pop('metadata')
        return FinancialAuditLog.log_transaction(**kwargs)

    @staticmethod
    def api_call(**kwargs) -> APIAuditLog:
        """Log third-party API call"""
        # Map 'metadata' parameter to 'extra_data' for compatibility
        if 'metadata' in kwargs:
            kwargs['extra_data'] = kwargs.pop('metadata')
        return APIAuditLog.log_api_call(**kwargs)

    @staticmethod
    def data_access(**kwargs) -> DataAccessLog:
        """Log sensitive data access"""
        return DataAccessLog.log_access(**kwargs)

    @staticmethod
    def security(**kwargs) -> SecurityEventLog:
        """Log security event"""
        # Map 'metadata' parameter to 'extra_data' for compatibility
        if 'metadata' in kwargs:
            kwargs['extra_data'] = kwargs.pop('metadata')
        return SecurityEventLog.log_event(**kwargs)

    @staticmethod
    def data_change(**kwargs) -> DataChangeLog:
        """Log data change event (wallet creation, freezing, payouts, etc.)"""
        # Map 'metadata' parameter to 'extra_data' for compatibility
        if 'metadata' in kwargs:
            kwargs['extra_data'] = kwargs.pop('metadata')
        return DataChangeLog.log_change(**kwargs)

    @staticmethod
    def compliance(**kwargs):
        """
        Log compliance decision using the ComplianceLogger.
        This avoids duplicate table definitions by using the existing logger.
        """
        from app.compliance.logger import ComplianceLogger
        return ComplianceLogger.log_decision(**kwargs)

    @staticmethod
    def log_role_change(user_id: int, old_role: str, new_role: str, changed_by: int, reason: str = None):
        """Log role change action"""
        try:
            from app.models.user import User
            target_user = User.query.get(user_id)
            performed_by_user = User.query.get(changed_by)
            
            audit_log = AuditLog(
                user_id=changed_by,
                action='role_change',
                resource_type='user_role',
                resource_id=user_id,
                details={
                    'target_user_id': user_id,
                    'target_username': target_user.username if target_user else None,
                    'old_role': old_role,
                    'new_role': new_role,
                    'reason': reason,
                    'performed_by_username': performed_by_user.username if performed_by_user else None
                },
                ip_address=getattr(request, 'remote_addr', None) if 'request' in globals() else None
            )
            db.session.add(audit_log)
            db.session.commit()
            return audit_log
        except Exception as e:
            logger.error(f"Error logging role change: {e}")
            db.session.rollback()
            return None

    @staticmethod
    def log_role_management_action(user_id: int, action: str, details: dict = None):
        """Log role management action (toggle permissions, etc.)"""
        try:
            from app.models.user import User
            performed_by_user = User.query.get(user_id)
            
            audit_log = AuditLog(
                user_id=user_id,
                action=action,
                resource_type='role_management',
                details=details or {},
                ip_address=getattr(request, 'remote_addr', None) if 'request' in globals() else None
            )
            db.session.add(audit_log)
            db.session.commit()
            return audit_log
        except Exception as e:
            logger.error(f"Error logging role management action: {e}")
            db.session.rollback()
            return None

    @staticmethod
    def get_recent_role_changes(limit: int = 10):
        """Get recent role change audit logs"""
        try:
            from app.models.user import User
            
            # Get role change logs
            logs = AuditLog.query.filter(
                AuditLog.action.in_(['role_change', 'assign_role', 'revoke_role'])
            ).order_by(AuditLog.created_at.desc()).limit(limit).all()
            
            result = []
            for log in logs:
                target_user = User.query.get(log.details.get('target_user_id')) if log.details else None
                performed_by_user = User.query.get(log.user_id) if log.user_id else None
                
                result.append({
                    'timestamp': log.created_at,
                    'action': log.action,
                    'target_user': target_user,
                    'performed_by_user': performed_by_user,
                    'old_role': log.details.get('old_role') if log.details else None,
                    'new_role': log.details.get('new_role') if log.details else None,
                    'reason': log.details.get('reason') if log.details else None
                })
            
            return result
        except Exception as e:
            logger.error(f"Error getting recent role changes: {e}")
            return []

    @staticmethod
    def get_role_management_audit_log(page: int = 1, per_page: int = 50):
        """Get paginated role management audit logs"""
        try:
            from app.models.user import User
            from flask_sqlalchemy.pagination import Pagination
            
            # Get role management logs
            query = AuditLog.query.filter(
                AuditLog.action.in_(['role_change', 'assign_role', 'revoke_role', 'toggle_admin_role_management', 'toggle_super_admin_role_management'])
            ).order_by(AuditLog.created_at.desc())
            
            # Paginate
            items = query.limit(per_page).offset((page - 1) * per_page).all()
            total = query.count()
            
            # Create pagination object
            pagination = Pagination(
                query=query,
                page=page,
                per_page=per_page,
                total=total,
                items=items
            )
            
            result = []
            for log in items:
                target_user = User.query.get(log.details.get('target_user_id')) if log.details else None
                performed_by_user = User.query.get(log.user_id) if log.user_id else None
                
                result.append({
                    'timestamp': log.created_at,
                    'action': log.action,
                    'target_user': target_user,
                    'performed_by_user': performed_by_user,
                    'old_role': log.details.get('old_role') if log.details else None,
                    'new_role': log.details.get('new_role') if log.details else None,
                    'reason': log.details.get('reason') if log.details else None,
                    'details': log.details
                })
            
            return pagination, result
        except Exception as e:
            logger.error(f"Error getting role management audit log: {e}")
            return None, []

    @staticmethod
    def moderator_view(entity_type: str, user_id: int, ip_address: str = None, **kwargs):
        """
        Log a moderator viewing action.
        """
        return AuditService.security(
            event_type=f"moderator_view_{entity_type}",
            severity="info",
            description=f"Moderator {user_id} viewed {entity_type}",
            user_id=user_id,
            ip_address=ip_address,
            **kwargs
        )
