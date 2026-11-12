"""
Admin Audit Service
Manages system-level audit logging for admin actions
"""

import json
from contextlib import contextmanager
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from flask import request
from sqlalchemy import func

from app.extensions import db
from app.wallet.models.admin_audit import AdminAuditLog


class AdminAuditService:
    """Service for managing admin audit logs"""

    # Sensitive field patterns that must never appear in audit logs (exact match on normalized key)
    SENSITIVE_KEYS = frozenset({
        'api_key', 'api_secret', 'api_password', 'api_token',
        'secret', 'password', 'passwd', 'passphrase',
        'access_token', 'refresh_token', 'authorization',
        'private_key', 'privatekey', 'priv_key',
        'webhook_secret', 'webhook_key',
        'sandbox_api_key', 'sandbox_api_secret',
        'live_api_key', 'live_api_secret',
        'vasp_api_key',
        'merchant_id', 'merchant_secret',
        'client_secret', 'client_id',
        'signing_key', 'encryption_key',
        'pin', 'otp', 'mfa_code',
    })

    # Keys that are SAFE boolean presence indicators - explicitly allowed through redaction
    SAFE_INDICATOR_KEYS = frozenset({
        'api_key_configured', 'api_secret_configured', 'api_password_configured',
        'api_token_configured', 'secret_configured', 'password_configured',
        'access_token_configured', 'refresh_token_configured', 'authorization_configured',
        'private_key_configured', 'webhook_secret_configured', 'webhook_key_configured',
        'sandbox_api_key_configured', 'sandbox_api_secret_configured',
        'live_api_key_configured', 'live_api_secret_configured',
        'vasp_api_key_configured',
        'merchant_id_configured', 'merchant_secret_configured',
        'client_secret_configured', 'client_id_configured',
        'signing_key_configured', 'encryption_key_configured',
        'pin_configured', 'otp_configured', 'mfa_code_configured',
        'webhook_configured', 'sandbox_configured', 'production_configured',
        'config_json_present', 'credentials_provided',
        'api_key_configured', 'api_secret_configured',
        'sandbox_api_key_configured', 'sandbox_api_secret_configured',
        'live_api_key_configured', 'live_api_secret_configured',
        'webhook_configured', 'webhook_secret_configured',
        'ip_whitelist_configured',
        'alert_emails_configured', 'vasp_endpoint_configured', 'vasp_api_key_configured',
    })

    # Keys that should be marked as updated without storing values
    SENSITIVE_MARKER_KEYS = frozenset({
        'config_json',  # may contain provider credentials
    })

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        """Check if a key name indicates sensitive data (exact match)"""
        key_lower = key.lower()
        # Explicitly allow safe boolean indicators
        if key_lower in AdminAuditService.SAFE_INDICATOR_KEYS:
            return False
        return any(pattern == key_lower for pattern in AdminAuditService.SENSITIVE_KEYS)

    @staticmethod
    def _sanitize_json_string(value: str, path: str = "") -> str:
        """Sanitize JSON object/array strings without needlessly reformatting safe values."""
        candidate = value.lstrip()
        if not candidate.startswith(("{", "[")):
            return value

        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            return value

        if not isinstance(parsed, (dict, list)):
            return value

        sanitized = AdminAuditService._sanitize_value(parsed, path)
        if sanitized == parsed:
            return value

        return json.dumps(sanitized, separators=(",", ":"), allow_nan=False)

    @staticmethod
    def _sanitize_value(value: Any, path: str = "") -> Any:
        """
        Recursively sanitize a value for audit logging.
        - Redacts sensitive fields
        - Handles nested dicts and lists
        - Converts non-JSON-serializable types
        - Hard fails on unsupported types
        """
        if value is None:
            return None

        # Handle dict - recursively sanitize
        if isinstance(value, dict):
            sanitized = {}
            for k, v in value.items():
                if AdminAuditService._is_sensitive_key(k):
                    # Redact sensitive fields
                    sanitized[k] = '[REDACTED]'
                elif k in AdminAuditService.SENSITIVE_MARKER_KEYS:
                    # For config_json, try to sanitize nested content
                    if isinstance(v, dict):
                        sanitized[k] = AdminAuditService._sanitize_value(v, f"{path}.{k}")
                    else:
                        sanitized[k] = '[REDACTED]'
                else:
                    sanitized[k] = AdminAuditService._sanitize_value(v, f"{path}.{k}")
            return sanitized

        # Handle list - recursively sanitize each element
        if isinstance(value, list):
            return [AdminAuditService._sanitize_value(item, f"{path}[]") for item in value]

        # Handle primitive types that need special serialization
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Decimal):
            # Exact decimal representation as string to preserve precision
            return format(value, 'f')
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, float):
            if not (value == value and abs(value) != float('inf')):  # NaN or infinity
                raise TypeError(f"Non-finite float value not allowed in audit: {value}")
            return value

        # Handle JSON-encoded values, including strings with leading whitespace.
        if isinstance(value, str):
            return AdminAuditService._sanitize_json_string(value, path)

        # Reject unsupported types explicitly
        if not isinstance(value, (str, int, bool, type(None))):
            raise TypeError(f"Unsupported type for audit serialization: {type(value).__name__}")

        return value

    @staticmethod
    def _serialize_audit_value(value: Any) -> Optional[str]:
        """
        Serialize a value to a JSON string for database storage.
        Handles:
        - None -> None
        - Already JSON string -> parse, sanitize, re-serialize
        - Dict/List/primitives -> JSON serialize
        - Dates/Decimals/UUIDs/Enums -> ISO format / exact string / enum value
        - Hard fails on unsupported types
        """
        if value is None:
            return None

        # Preserve already-valid JSON strings when no redaction is needed.
        # Parse with leading-whitespace tolerance so secrets cannot bypass
        # sanitization by prefixing an otherwise valid JSON document with spaces.
        if isinstance(value, str):
            return AdminAuditService._sanitize_json_string(value)

        # Sanitize and serialize structured values
        sanitized = AdminAuditService._sanitize_value(value)
        try:
            return json.dumps(sanitized, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError) as e:
            # Hard failure - don't swallow serialization bugs
            raise TypeError(f"Audit serialization failed: {e}") from e

    @staticmethod
    def log_action(
        admin_id: int,
        admin_name: str,
        admin_role: str,
        action_type: str,
        action_category: str,
        target_type: str,
        target_id: Optional[str] = None,
        target_name: Optional[str] = None,
        old_value: Any = None,
        new_value: Any = None,
        reason: Optional[str] = None
    ) -> AdminAuditLog:
        """
        Log an admin action for audit trail.

        IMPORTANT: This method only adds and flushes the audit record.
        It does NOT commit or rollback - the caller owns the transaction.

        Args:
            admin_id: ID of admin performing action
            admin_name: Name of admin
            admin_role: Role of admin
            action_type: Type of action (approve, reject, configure, modify)
            action_category: Category of action (aggregator, fraud_detection, etc.)
            target_type: Type of target (aggregator, user, transaction)
            target_id: ID of target
            target_name: Name of target
            old_value: Previous state (dict, list, primitive, or JSON string)
            new_value: New state (dict, list, primitive, or JSON string)
            reason: Reason for action

        Returns:
            AdminAuditLog object (flushed, not committed)
        """
        audit_log = AdminAuditLog(
            admin_id=admin_id,
            admin_name=admin_name,
            admin_role=admin_role,
            action_type=action_type,
            action_category=action_category,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            old_value=AdminAuditService._serialize_audit_value(old_value),
            new_value=AdminAuditService._serialize_audit_value(new_value),
            reason=reason,
            ip_address=request.remote_addr if request else None,
            user_agent=request.user_agent.string if request and request.user_agent else None,
            created_at=datetime.now(timezone.utc)
        )

        db.session.add(audit_log)
        db.session.flush()  # Surface DB errors (FK, bad JSON) NOW, no commit
        return audit_log

    @staticmethod
    @contextmanager
    def audited_change():
        """
        Context manager for atomic business change + audit logging.
        
        Usage:
            with AdminAuditService.audited_change():
                # Make business changes
                aggregator.mode = new_mode
                # Log audit
                AdminAuditService.log_action(
                    admin_id=..., action_type="configure", ...,
                    old_value=aggregator.to_audit_snapshot(before),
                    new_value=aggregator.to_audit_snapshot(),
                )
            # If we reach here, both business change and audit are committed
            # If any exception occurs, both are rolled back
        """
        try:
            yield
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    @staticmethod
    def get_audit_logs(
        admin_id: Optional[int] = None,
        action_type: Optional[str] = None,
        action_category: Optional[str] = None,
        target_type: Optional[str] = None,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get audit logs with filters
        """
        try:
            query = AdminAuditLog.query

            # Apply filters
            if admin_id:
                query = query.filter(AdminAuditLog.admin_id == admin_id)
            if action_type:
                query = query.filter(AdminAuditLog.action_type == action_type)
            if action_category:
                query = query.filter(AdminAuditLog.action_category == action_category)
            if target_type:
                query = query.filter(AdminAuditLog.target_type == target_type)

            # Date filter
            date_threshold = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(AdminAuditLog.created_at >= date_threshold)

            # Order by most recent
            query = query.order_by(AdminAuditLog.created_at.desc())

            # Apply limit
            query = query.limit(limit)

            logs = query.all()
            return [log.to_dict() for log in logs]
        except Exception as e:
            raise e

    @staticmethod
    def get_audit_summary(days: int = 30) -> Dict[str, Any]:
        """
        Get summary statistics for audit logs
        """
        try:
            date_threshold = datetime.now(timezone.utc) - timedelta(days=days)

            total_actions = AdminAuditLog.query.filter(
                AdminAuditLog.created_at >= date_threshold
            ).count()

            actions_by_type = db.session.query(
                AdminAuditLog.action_type,
                func.count(AdminAuditLog.id)
            ).filter(
                AdminAuditLog.created_at >= date_threshold
            ).group_by(AdminAuditLog.action_type).all()

            actions_by_category = db.session.query(
                AdminAuditLog.action_category,
                func.count(AdminAuditLog.id)
            ).filter(
                AdminAuditLog.created_at >= date_threshold
            ).group_by(AdminAuditLog.action_category).all()

            return {
                'total_actions': total_actions,
                'actions_by_type': dict(actions_by_type),
                'actions_by_category': dict(actions_by_category),
                'days': days
            }
        except Exception as e:
            raise e