#app/audit/forensic_audit.py
"""
Forensic Audit Service for comprehensive audit trail tracking.
Tracks attempt vs completion timestamps for compliance with Bank of Uganda and FIA Uganda requirements.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
import uuid

# Try to import from comprehensive_audit, fall back to mocks if not available
try:
    from app.audit.comprehensive_audit import DataChangeLog, SecurityEventLog, AuditSeverity

    HAS_COMPREHENSIVE_AUDIT = True
except ImportError:
    # Create mock classes for testing
    class DataChangeLog:
        @staticmethod
        def log_change(*args, **kwargs):
            pass


    class SecurityEventLog:
        @staticmethod
        def log_event(*args, **kwargs):
            pass


    class AuditSeverity:
        INFO = "info"
        WARNING = "warning"
        CRITICAL = "critical"
        SECURITY = "security"


    HAS_COMPREHENSIVE_AUDIT = False


class ForensicAuditService:
    """Centralized forensic audit logging with attempt vs completion tracking."""

    @staticmethod
    def log_attempt(
            entity_type: str,
            entity_id: str,
            action: str,
            user_id: Optional[int] = None,
            details: Optional[Dict] = None,
            correlation_id: Optional[str] = None,
            ip_address: Optional[str] = None,
            user_agent: Optional[str] = None,
            session_id: Optional[str] = None,
            risk_score: Optional[int] = None
    ) -> str:
        """Log when user INITIATES an action, capturing actor vs effective identity."""
        audit_id = str(uuid.uuid4())

        # Capture identity and request metadata
        actor_id = None
        effective_id = None
        try:
            from app.core.context import RequestContext
            actor = RequestContext.get_actor()
            effective = RequestContext.get_effective_user()
            actor_id = getattr(actor, 'id', None)
            effective_id = getattr(effective, 'id', None)
        except Exception:
            pass
        try:
            from flask import request as flask_request, session as flask_session
            ip_address = ip_address or (flask_request.remote_addr if flask_request else None)
            user_agent = user_agent or (flask_request.user_agent.string if flask_request and flask_request.user_agent else None)
            session_id = session_id or flask_session.get('session_id') or flask_session.get('_id') or getattr(flask_session, 'sid', None)
        except Exception:
            pass

        # Default changed_by to actor when available; fallback to provided user_id
        changed_by = actor_id or user_id

        # Create a DataChangeLog entry with attempted_at timestamp
        DataChangeLog.log_change(
            entity_type=entity_type,
            entity_id=str(entity_id),
            operation=f"attempt_{action}",
            old_value=None,
            new_value=details if isinstance(details, dict) else {'details': str(details)} if details else None,
            changed_by=changed_by,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data={
                "audit_id": audit_id,
                "status": "pending",
                "attempted_at": datetime.now(timezone.utc).isoformat(),
                "correlation_id": correlation_id or audit_id,
                "session_id": session_id,
                "risk_score": risk_score,
                "details": details,
                "actor_user_id": actor_id,
                "effective_user_id": effective_id,
                "action": action,
            }
        )

        # Also log to SecurityEventLog for suspicious activity tracking
        if risk_score and risk_score > 70:
            SecurityEventLog.log_event(
                event_type=f"high_risk_attempt_{action}",
                severity=AuditSeverity.WARNING,
                description=f"High risk attempt detected for {entity_type} {entity_id}",
                user_id=actor_id or user_id,
                ip_address=ip_address,
                extra_data={"audit_id": audit_id, "risk_score": risk_score, "effective_user_id": effective_id}
            )

        return audit_id

    @staticmethod
    def log_completion(
            audit_id: str,
            status: str = 'completed',
            reviewed_by: Optional[int] = None,
            review_notes: Optional[str] = None,
            result_details: Optional[Dict] = None
    ) -> bool:
        """Log when action is COMPLETED/APPLIED, including identity and request metadata."""
        try:
            # Collect identity and request context
            actor_id = None
            effective_id = None
            ip_address = None
            user_agent = None
            try:
                from app.core.context import RequestContext
                actor = RequestContext.get_actor()
                effective = RequestContext.get_effective_user()
                actor_id = getattr(actor, 'id', None)
                effective_id = getattr(effective, 'id', None)
            except Exception:
                pass
            try:
                from flask import request as flask_request
                ip_address = flask_request.remote_addr if flask_request else None
                user_agent = flask_request.user_agent.string if flask_request and flask_request.user_agent else None
            except Exception:
                pass

            # Try to get current_app if Flask context exists
            try:
                from flask import current_app
                if current_app:
                    current_app.logger.info(f"Logging completion for audit_id: {audit_id}, status: {status}")
            except Exception:
                pass

            # Log completion as a separate DataChangeLog entry
            DataChangeLog.log_change(
                entity_type="audit_trail",
                entity_id=audit_id,
                operation="completion",
                old_value="pending",
                new_value=status,
                changed_by=reviewed_by or actor_id,
                ip_address=ip_address,
                user_agent=user_agent,
                extra_data={
                    "audit_id": audit_id,
                    "status": status,
                    "reviewed_by": reviewed_by or actor_id,
                    "review_notes": review_notes,
                    "reviewed_at": datetime.now(timezone.utc).isoformat(),
                    "result_details": result_details,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "actor_user_id": actor_id,
                    "effective_user_id": effective_id,
                }
            )

            return True
        except Exception as e:
            # Try to log the error if Flask context exists
            try:
                from flask import current_app
                if current_app:
                    current_app.logger.error(f"Error logging completion: {e}")
            except Exception:
                pass
            return False

    @staticmethod
    def log_blocked(
            entity_type: str,
            entity_id: str,
            action: str,
            user_id: Optional[int] = None,
            reason: Optional[str] = None,
            attempted_value: Optional[str] = None,
            old_value: Optional[str] = None,
            ip_address: Optional[str] = None,
            user_agent: Optional[str] = None
    ) -> str:
        """Log when action is BLOCKED (like KYC immutability), capturing actor/effective identity."""
        audit_id = str(uuid.uuid4())

        # Capture identity and request metadata
        actor_id = None
        effective_id = None
        try:
            from app.core.context import RequestContext
            actor = RequestContext.get_actor()
            effective = RequestContext.get_effective_user()
            actor_id = getattr(actor, 'id', None)
            effective_id = getattr(effective, 'id', None)
        except Exception:
            pass
        try:
            from flask import request as flask_request
            ip_address = ip_address or (flask_request.remote_addr if flask_request else None)
            user_agent = user_agent or (flask_request.user_agent.string if flask_request and flask_request.user_agent else None)
        except Exception:
            pass

        DataChangeLog.log_change(
            entity_type=entity_type,
            entity_id=str(entity_id),
            operation=f"blocked_{action}",
            old_value=old_value,
            new_value=attempted_value,
            changed_by=actor_id or user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data={
                "audit_id": audit_id,
                "status": "blocked",
                "attempted_at": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "review_notes": reason,
                "blocked_reason": reason,
                "actor_user_id": actor_id,
                "effective_user_id": effective_id,
                "action": action,
            }
        )

        # Also log to SecurityEventLog for compliance
        SecurityEventLog.log_event(
            event_type=f"blocked_{action}",
            severity=AuditSeverity.WARNING,
            description=f"Action blocked for {entity_type} {entity_id}: {reason}",
            user_id=actor_id or user_id,
            ip_address=ip_address,
            extra_data={"audit_id": audit_id, "effective_user_id": effective_id}
        )

        return audit_id

    @staticmethod
    def get_audit_timeline(
            entity_type: str,
            entity_id: str,
            days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get complete forensic timeline for an entity."""
        from app.audit.comprehensive_audit import DataChangeLog

        since = datetime.now(timezone.utc) - timedelta(days=days)

        logs = DataChangeLog.query.filter(
            DataChangeLog.entity_type == entity_type,
            DataChangeLog.entity_id == str(entity_id),
            DataChangeLog.created_at >= since
        ).order_by(DataChangeLog.created_at.desc()).all()

        timeline = []
        for log in logs:
            extra = log.extra_data or {}
            timeline.append({
                'audit_id': extra.get('audit_id'),
                'action': log.operation,
                'status': extra.get('status', 'unknown'),
                'attempted_at': extra.get('attempted_at'),
                'completed_at': extra.get('completed_at'),
                'reviewed_by': extra.get('reviewed_by'),
                'review_notes': extra.get('review_notes'),
                'details': extra.get('details'),
                'old_value': log.old_value,
                'new_value': log.new_value,
                'created_at': log.created_at
            })

        return timeline

    @staticmethod
    def get_pending_reviews(
            entity_type: Optional[str] = None,
            limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get pending items awaiting compliance review."""
        from app.audit.comprehensive_audit import DataChangeLog
        import json

        query = DataChangeLog.query.filter(
            DataChangeLog.extra_data['status'].as_string() == 'pending'
        )

        if entity_type:
            query = query.filter(DataChangeLog.entity_type == entity_type)

        logs = query.order_by(DataChangeLog.created_at.asc()).limit(limit).all()

        pending = []
        for log in logs:
            extra = log.extra_data or {}
            # Handle timezone-aware/native datetime subtraction
            created_at = log.created_at
            if created_at.tzinfo is None:
                # If created_at is naive, assume UTC
                created_at = created_at.replace(tzinfo=timezone.utc)

            waiting_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600

            pending.append({
                'audit_id': extra.get('audit_id'),
                'entity_type': log.entity_type,
                'entity_id': log.entity_id,
                'action': log.operation,
                'attempted_at': extra.get('attempted_at'),
                'waiting_hours': waiting_hours,
                'user_id': log.changed_by,
                'details': extra.get('details'),
                'created_at': log.created_at
            })

        return pending

    @staticmethod
    def get_blocked_attempts(
            since: Optional[datetime] = None,
            limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get blocked attempts from audit logs."""
        try:
            from app.audit.comprehensive_audit import DataChangeLog

            # Default to last 24 hours
            if since is None:
                since = datetime.now(timezone.utc) - timedelta(hours=24)
            else:
                # Ensure since is timezone-aware
                if since.tzinfo is None:
                    since = since.replace(tzinfo=timezone.utc)

            # Query for blocked attempts
            logs = DataChangeLog.query.filter(
                DataChangeLog.operation.like('blocked_%'),
                DataChangeLog.created_at >= since
            ).order_by(DataChangeLog.created_at.desc()).limit(limit).all()

            blocked_attempts = []
            for log in logs:
                extra = log.extra_data or {}
                blocked_attempts.append({
                    'audit_id': extra.get('audit_id'),
                    'entity_type': log.entity_type,
                    'entity_id': log.entity_id,
                    'action': log.operation.replace('blocked_', ''),
                    'blocked_reason': extra.get('blocked_reason'),
                    'attempted_at': extra.get('attempted_at'),
                    'blocked_at': log.created_at.isoformat() if log.created_at else None,
                    'user_id': log.changed_by,
                    'ip_address': log.ip_address,
                    'details': extra.get('details')
                })

            return blocked_attempts
        except Exception as e:
            # Log error but return empty list
            try:
                from flask import current_app
                if current_app:
                    current_app.logger.error(f"Error getting blocked attempts: {e}")
            except:
                pass
            return []

    @staticmethod
    def get_suspicious_patterns(
            hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Detect suspicious patterns."""
        patterns = []

        # This would implement actual pattern detection
        # For now, return empty list
        return patterns

    @staticmethod
    def calculate_risk_score(
            user_id: Optional[int],
            action: str,
            entity_type: str,
            details: Dict
    ) -> int:
        """Calculate risk score for an audit event."""
        risk_score = 0

        # Basic risk scoring logic
        if action in ['login', 'password_reset', 'kyc_submission']:
            risk_score += 10

        if entity_type in ['wallet', 'transaction', 'kyc']:
            risk_score += 20

        # Add more sophisticated logic here
        return min(risk_score, 100)
