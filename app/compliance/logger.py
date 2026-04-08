# app/compliance/logger.py

"""
Compliance Logger - Uses Comprehensive Audit System
---------------------------------------------------
Centralized logging for KYC decisions, transaction limits, and sensitive data access.
All logs go through the unified audit system for consistency.
"""

import logging
from datetime import datetime
from flask import request
from app.extensions import db
from app.audit.comprehensive_audit import AuditService, AuditSeverity

logger = logging.getLogger("compliance")


class ComplianceLogger:
    """
    Centralized service for logging compliance events.
    Uses the unified AuditService from comprehensive_audit.py.
    """

    @staticmethod
    def log_kyc_decision(
            user_id, decision, kyc_level, reviewer_id=None,
            rejection_reason=None, ip=None, user_agent=None
    ):
        """
        Log KYC approval or rejection
        """
        ip = ip or (request.remote_addr if request else None)
        user_agent = user_agent or (request.user_agent.string if request and request.user_agent else None)

        AuditService.compliance(
            entity_type="user",
            entity_id=user_id,
            check_type="kyc",
            result=decision,
            details={
                "kyc_level": kyc_level,
                "rejection_reason": rejection_reason,
                "reviewer_id": reviewer_id
            },
            ip_address=ip,
            user_agent=user_agent
        )

        logger.info(f"KYC {decision.upper()} | user={user_id} | level={kyc_level} | reviewer={reviewer_id}")

    @staticmethod
    def log_transaction(
            transaction_id, user_id, amount, currency,
            transaction_type, status, ip=None, user_agent=None, metadata=None
    ):
        """
        Log critical financial transaction
        """
        ip = ip or (request.remote_addr if request else None)
        user_agent = user_agent or (request.user_agent.string if request and request.user_agent else None)

        # Use financial audit for transactions
        AuditService.financial(
            transaction_id=transaction_id,
            transaction_type=transaction_type,
            amount=amount,
            currency=currency,
            status=status,
            to_user_id=user_id,
            ip_address=ip,
            user_agent=user_agent,
            metadata={
                "compliance_log": True,
                "client_metadata": metadata or {}
            }
        )

        logger.info(f"Transaction {transaction_type} | user={user_id} | amount={amount} {currency} | status={status}")

    @staticmethod
    def log_data_access(
            accessed_by, subject_user_id, access_type, data_category,
            purpose, legal_basis, ip=None, user_agent=None
    ):
        """
        Log access to sensitive user data (GDPR / Data Privacy)
        """
        ip = ip or (request.remote_addr if request else None)
        user_agent = user_agent or (request.user_agent.string if request and request.user_agent else None)

        from app.audit.comprehensive_audit import DataAccessType

        access_type_map = {
            "READ": DataAccessType.READ,
            "EXPORT": DataAccessType.EXPORT,
            "DELETE": DataAccessType.DELETE,
            "MODIFY": DataAccessType.MODIFY
        }

        AuditService.data_access(
            accessed_by=accessed_by,
            subject_user_id=subject_user_id,
            access_type=access_type_map.get(access_type.upper(), DataAccessType.READ),
            data_category=data_category,
            purpose=purpose,
            legal_basis=legal_basis,
            ip_address=ip,
            user_agent=user_agent
        )

        logger.info(
            f"Data Access | by={accessed_by} | subject={subject_user_id} | category={data_category} | purpose={purpose}")

    @staticmethod
    def log_security_event(
            user_id=None, event_type=None, severity="INFO",
            description=None, metadata=None, ip=None, user_agent=None
    ):
        """
        Log security incidents (e.g., brute force, suspicious activity)
        """
        ip = ip or (request.remote_addr if request else None)
        user_agent = user_agent or (request.user_agent.string if request and request.user_agent else None)

        severity_map = {
            "INFO": AuditSeverity.INFO,
            "WARNING": AuditSeverity.WARNING,
            "CRITICAL": AuditSeverity.CRITICAL,
            "SECURITY": AuditSeverity.SECURITY
        }

        AuditService.security(
            event_type=event_type,
            severity=severity_map.get(severity.upper(), AuditSeverity.INFO),
            description=description,
            user_id=user_id,
            ip_address=ip,
            user_agent=user_agent,
            metadata=metadata or {}
        )

        # Dynamic logging based on severity
        log_level = logging.INFO
        if severity.upper() == "CRITICAL":
            log_level = logging.CRITICAL
        elif severity.upper() == "WARNING":
            log_level = logging.WARNING

        logger.log(
            log_level,
            f"Security Event | user={user_id} | type={event_type} | severity={severity} | desc={description}"
        )

    @staticmethod
    def log_decision(
            entity_id: int,
            entity_type: str,
            operation: str,
            decision: str,
            requirement_key: str = None,
            compliance_level: int = None,
            risk_tier: str = None,
            context: dict = None
    ):
        """
        Generic compliance decision logging.
        Compatible with the existing call in services.py
        """
        AuditService.compliance(
            entity_type=entity_type,
            entity_id=entity_id,
            check_type=operation,
            result=decision,
            details={
                "requirement_key": requirement_key,
                "compliance_level": compliance_level,
                "risk_tier": risk_tier,
                "context": context or {}
            }
        )

        logger.info(
            f"Compliance Decision | {entity_type}={entity_id} | operation={operation} | decision={decision}"
        )
