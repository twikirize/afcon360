"""
Rate Limit Breach Notification Service
Sends alerts when rate limit breaches exceed configured thresholds.
"""

import logging
from datetime import datetime, timezone, timedelta

from flask import request, current_app
from flask_login import current_user

from app.extensions import db, mail
from app.admin.owner.models import RateLimitBreach, RateLimitSettings
from app.audit.comprehensive_audit import AuditService, AuditSeverity
from app.models.notification import Notification, NotificationType

logger = logging.getLogger(__name__)


class RateLimitNotificationService:
    """Service for handling rate limit breach notifications"""

    BREACH_CLEANUP_DAYS = 30

    @staticmethod
    def record_breach(
        identity_type: str,
        identity_value: str,
        endpoint: str = None,
        method: str = None,
        limit_exceeded: str = None,
        blocked: bool = False,
        block_duration_minutes: int = None,
    ) -> RateLimitBreach:
        """Record a rate limit breach and trigger notifications if configured"""
        try:
            breach = RateLimitBreach(
                identity_type=identity_type,
                identity_value=identity_value,
                endpoint=endpoint,
                method=method,
                limit_exceeded=limit_exceeded,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request else None,
                blocked=blocked,
                block_duration_minutes=block_duration_minutes,
            )
            db.session.add(breach)
            db.session.commit()

            # Check if alerting is enabled and threshold exceeded
            RateLimitNotificationService._check_and_notify(breach)

            return breach
        except Exception as e:
            logger.error(f"Failed to record rate limit breach: {e}")
            db.session.rollback()
            return None

    @staticmethod
    def _check_and_notify(breach: RateLimitBreach):
        """Check breach against threshold and send notifications"""
        try:
            alert_on_breach = RateLimitSettings.get_setting('alert_on_breach', False)
            if not alert_on_breach:
                return

            threshold = RateLimitSettings.get_setting('alert_threshold_per_minute', 100)

            # Count breaches in the last minute for this identity
            one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
            recent_count = RateLimitBreach.query.filter(
                RateLimitBreach.identity_type == breach.identity_type,
                RateLimitBreach.identity_value == breach.identity_value,
                RateLimitBreach.created_at >= one_minute_ago,
            ).count()

            if recent_count >= threshold:
                RateLimitNotificationService._send_alert(breach, recent_count)
        except Exception as e:
            logger.error(f"Failed to check/notify rate limit breach: {e}")

    @staticmethod
    def _send_alert(breach: RateLimitBreach, recent_count: int):
        """Send email and in-app notification for breach threshold exceeded"""
        try:
            # Mark as notified
            breach.notified = True
            breach.notified_at = datetime.now(timezone.utc)
            db.session.commit()

            # Log to security audit
            AuditService.security(
                event_type='rate_limit_breach_alert',
                severity=AuditSeverity.WARNING,
                description=f"Rate limit breach threshold exceeded for {breach.identity_type}:{breach.identity_value} — {recent_count} breaches/min",
                user_id=breach.owner_id,
                ip_address=breach.ip_address,
                extra_data={
                    'identity_type': breach.identity_type,
                    'identity_value': breach.identity_value,
                    'endpoint': breach.endpoint,
                    'method': breach.method,
                    'limit_exceeded': breach.limit_exceeded,
                    'recent_count': recent_count,
                    'blocked': breach.blocked,
                }
            )

            # Send email to owner
            RateLimitNotificationService._send_email(breach, recent_count)

            # Create in-app notification for owner
            RateLimitNotificationService._create_in_app_notification(breach, recent_count)

        except Exception as e:
            logger.error(f"Failed to send rate limit breach alert: {e}")

    @staticmethod
    def _send_email(breach: RateLimitBreach, recent_count: int):
        """Send email alert to owner"""
        try:
            from flask_mail import Message

            owner = breach.owner
            if not owner or not owner.email:
                return

            msg = Message(
                subject=f"[AFCON360] Rate Limit Breach Alert — {breach.identity_type}:{breach.identity_value}",
                sender=current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@example.com'),
                recipients=[owner.email],
                body=(
                    f"Rate limit breach threshold exceeded.\n\n"
                    f"Identity: {breach.identity_type}: {breach.identity_value}\n"
                    f"Endpoint: {breach.endpoint or 'N/A'}\n"
                    f"Method: {breach.method or 'N/A'}\n"
                    f"Limit exceeded: {breach.limit_exceeded or 'N/A'}\n"
                    f"Breaches in last minute: {recent_count}\n"
                    f"IP Address: {breach.ip_address or 'N/A'}\n"
                    f"Blocked: {breach.blocked}\n"
                    f"Time: {datetime.now(timezone.utc).isoformat()}\n\n"
                    f"Review the rate limiting configuration at /admin/owner/configure-rate-limiting"
                ),
            )
            mail.send(msg)
            logger.info(f"Rate limit breach email sent to {owner.email}")
        except Exception as e:
            logger.error(f"Failed to send rate limit breach email: {e}")

    @staticmethod
    def _create_in_app_notification(breach: RateLimitBreach, recent_count: int):
        """Create in-app notification for owner"""
        try:
            owner = breach.owner
            if not owner:
                return

            notification = Notification(
                user_id=owner.id,
                type=NotificationType.SECURITY_ALERT,
                title="Rate Limit Breach Threshold Exceeded",
                message=(
                    f"{breach.identity_type}:{breach.identity_value} has exceeded "
                    f"the rate limit threshold with {recent_count} breaches/min. "
                    f"Endpoint: {breach.endpoint or 'N/A'}"
                ),
                link="/admin/owner/configure-rate-limiting",
                priority="high",
                channels=["in_app"],
                data={
                    'identity_type': breach.identity_type,
                    'identity_value': breach.identity_value,
                    'endpoint': breach.endpoint,
                    'recent_count': recent_count,
                    'blocked': breach.blocked,
                },
            )
            db.session.add(notification)
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to create in-app notification: {e}")
            db.session.rollback()

    @staticmethod
    def get_recent_breaches(minutes: int = 60, limit: int = 50):
        """Get recent rate limit breaches"""
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return RateLimitBreach.query.filter(
            RateLimitBreach.created_at >= since
        ).order_by(RateLimitBreach.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_breach_summary(minutes: int = 60):
        """Get breach summary for dashboard"""
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        breaches = RateLimitBreach.query.filter(
            RateLimitBreach.created_at >= since
        ).all()

        total = len(breaches)
        blocked = sum(1 for b in breaches if b.blocked)
        notified = sum(1 for b in breaches if b.notified)
        unique_identities = len(set((b.identity_type, b.identity_value) for b in breaches))

        by_endpoint = {}
        for b in breaches:
            ep = b.endpoint or 'unknown'
            by_endpoint[ep] = by_endpoint.get(ep, 0) + 1

        return {
            'total': total,
            'blocked': blocked,
            'notified': notified,
            'unique_identities': unique_identities,
            'by_endpoint': dict(sorted(by_endpoint.items(), key=lambda x: x[1], reverse=True)),
            'threshold_exceeded_count': notified,
        }

    @staticmethod
    def cleanup_old_breaches():
        """Remove breach records older than retention period"""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=RateLimitNotificationService.BREACH_CLEANUP_DAYS)
            old = RateLimitBreach.query.filter(RateLimitBreach.created_at < cutoff).delete(synchronize_session=False)
            db.session.commit()
            if old:
                logger.info(f"Cleaned up {old} old rate limit breach records")
        except Exception as e:
            logger.error(f"Failed to cleanup old breach records: {e}")
            db.session.rollback()