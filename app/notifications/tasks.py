"""
AFCON360 Notification Celery Tasks

Robust async workers for notification delivery, retry scheduling,
and maintenance. Registered in app/celery_app.py beat_schedule.
"""

import logging
from datetime import datetime, timezone, timedelta

from celery import shared_task
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db
from app.notifications.models import (
    Notification, NotificationStatus, NotificationType,
)
from app.notifications.services import NotificationService
from app.notifications.utils import calculate_backoff

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
DEFAULT_RETRY_DELAY = 60


@shared_task(
    bind=True,
    name="notifications.send_notification",
    max_retries=MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def send_notification_task(self, notification_id: int) -> dict:
    """
    Asynchronously deliver a single notification record.
    Retries with exponential backoff on failure.
    """
    app = create_app()
    with app.app_context():
        try:
            notification = db.session.get(Notification, notification_id)
            if not notification:
                logger.warning(f"Notification {notification_id} not found, skipping")
                return {"status": "not_found", "notification_id": notification_id}

            if notification.status == NotificationStatus.DELIVERED:
                logger.info(f"Notification {notification_id} already delivered, skipping")
                return {"status": "already_delivered", "notification_id": notification_id}

            if notification.status == NotificationStatus.CANCELLED:
                logger.info(f"Notification {notification_id} cancelled, skipping")
                return {"status": "cancelled", "notification_id": notification_id}

            if notification.scheduled_for and notification.scheduled_for > datetime.now(timezone.utc):
                logger.info(f"Notification {notification_id} not yet scheduled, deferring")
                self.retry(countdown=30)
                return {"status": "deferred", "notification_id": notification_id}

            notification.increment_attempts()
            notification.status = NotificationStatus.PENDING
            db.session.commit()

            result = NotificationService.send(
                user_id=notification.user_id,
                notification_type=notification.type,
                title=notification.subject or notification.title,
                message=notification.body,
                data=notification.context or {},
                channels=[notification.channel] if notification.channel else ['in_app'],
                link=notification.link,
                priority=notification.priority,
            )

            if result:
                logger.info(f"Notification {notification_id} delivered successfully")
                return {"status": "delivered", "notification_id": notification_id}
            else:
                raise Exception(f"NotificationService.send returned None for {notification_id}")

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"DB error processing notification {notification_id}: {e}")
            self.retry(countdown=calculate_backoff(self.request.retries))
            return {"status": "retry", "notification_id": notification_id, "error": str(e)}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to process notification {notification_id}: {e}", exc_info=True)
            try:
                notification = db.session.get(Notification, notification_id)
                if notification:
                    notification.mark_failed(str(e))
                    db.session.commit()
            except Exception:
                db.session.rollback()
            raise self.retry(exc=e, countdown=calculate_backoff(self.request.retries))


@shared_task(
    name="notifications.send_bulk",
)
def send_bulk_task(notification_ids: list) -> dict:
    """
    Process multiple notifications concurrently.
    """
    app = create_app()
    with app.app_context():
        logger.info(f"[Celery] Processing bulk notification batch size: {len(notification_ids)}")
        results = {"processed": 0, "failed": 0, "notification_ids": []}
        for nid in notification_ids:
            try:
                result = send_notification_task.delay(nid)
                results["notification_ids"].append({"id": nid, "task_id": result.id})
                results["processed"] += 1
            except Exception as e:
                logger.error(f"Failed to queue notification {nid}: {e}")
                results["failed"] += 1
        return results


@shared_task(
    name="notifications.schedule_reminders",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def schedule_reminders_task(self) -> dict:
    """
    Celery Beat task: queries pending notifications where scheduled_for <= now
    and dispatches them.
    """
    app = create_app()
    with app.app_context():
        try:
            now = datetime.now(timezone.utc)
            pending = Notification.query.filter(
                Notification.scheduled_for <= now,
                Notification.status == NotificationStatus.PENDING,
            ).all()

            dispatched = 0
            for notification in pending:
                try:
                    send_notification_task.delay(notification.id)
                    dispatched += 1
                except Exception as e:
                    logger.error(f"Failed to dispatch reminder {notification.id}: {e}")

            logger.info(f"Dispatched {dispatched} scheduled reminders out of {len(pending)} pending")
            return {"dispatched": dispatched, "pending": len(pending)}
        except SQLAlchemyError as e:
            logger.error(f"DB error in schedule_reminders: {e}")
            self.retry(exc=e, countdown=60)
            return {"status": "error", "error": str(e)}


@shared_task(
    name="notifications.cleanup_old",
)
def cleanup_old_notifications_task(days: int = 30) -> dict:
    """
    Celery Beat task: archives notification logs older than `days` days
    and soft-deletes old read notifications.
    """
    app = create_app()
    with app.app_context():
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Soft-delete old read notifications
            old_read = Notification.query.filter(
                Notification.is_read == True,
                Notification.read_at < cutoff,
                Notification.is_deleted == False,
            ).all()
            soft_deleted = len(old_read)
            for notification in old_read:
                notification.soft_delete()

            # Delete old notification logs
            from app.notifications.models import NotificationLog
            old_logs = NotificationLog.query.filter(
                NotificationLog.attempted_at < cutoff,
            ).all()
            log_count = len(old_logs)
            for log in old_logs:
                db.session.delete(log)

            if soft_deleted > 0 or log_count > 0:
                db.session.commit()

            logger.info(
                f"Cleanup complete: soft_deleted={soft_deleted}, "
                f"logs_deleted={log_count}"
            )
            return {"soft_deleted": soft_deleted, "logs_deleted": log_count}
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"DB error in cleanup_old_notifications: {e}")
            return {"status": "error", "error": str(e)}


@shared_task(
    name="notifications.resend_failed",
)
def resend_failed_task(max_retries: int = 3) -> dict:
    """
    Celery Beat task: resend failed notifications with exponential backoff.
    """
    app = create_app()
    with app.app_context():
        try:
            count = NotificationService.resend_failed(max_retries=max_retries)
            logger.info(f"Resent {count} failed notifications")
            return {"resent": count}
        except Exception as e:
            logger.error(f"Failed to resend notifications: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}