"""
AFCON360 Notification Celery Tasks

Robust async workers for notification delivery, retry scheduling,
and maintenance. Registered in app/celery_app.py beat_schedule.
"""

import logging
from datetime import datetime, timezone, timedelta

from celery import shared_task
from sqlalchemy.exc import SQLAlchemyError

from app.tasks.context import _get_task_flask_app, with_flask_app_context
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
    app = _get_task_flask_app()
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
                title=notification.subject,
                message=notification.body,
                data=notification.context or {},
                channels=[notification.channel] if notification.channel else ['in_app'],
                link=notification.link,
                priority=notification.priority,
                module=notification.module,
                existing_notification=notification,
            )

            if result is None:
                raise RuntimeError("notification_service_returned_no_result")

            if result.status == NotificationStatus.FAILED:
                # A handler can return a failed result instead of raising.
                # Do not let Celery report that delivery as SUCCESS.
                raise RuntimeError("notification_delivery_failed")

            status_value = getattr(result.status, "value", result.status)
            logger.info(
                "Notification task completed (notification_id=%s, status=%s)",
                notification_id,
                status_value,
            )
            return {"status": status_value, "notification_id": notification_id}

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(
                "DB error processing notification %s (exception_type=%s)",
                notification_id, type(e).__name__,
            )
            self.retry(countdown=calculate_backoff(self.request.retries))
            return {"status": "retry", "notification_id": notification_id, "error_code": type(e).__name__}
        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to process notification %s (exception_type=%s)",
                notification_id, type(e).__name__, exc_info=True,
            )
            try:
                notification = db.session.get(Notification, notification_id)
                if notification:
                    notification.mark_failed(str(getattr(e, "code", type(e).__name__))[:80])
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
    app = _get_task_flask_app()
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
    name="notifications.notify_kyc_submitted",
)
def notify_kyc_submitted_task(user_id: int, kyc_record_id: int) -> dict:
    """
    Fan out KYC *submission* notifications (submitter + review team) off the
    request thread. Enqueued by dispatch_notification when a worker is present.
    """
    app = _get_task_flask_app()
    with app.app_context():
        try:
            from app.notifications.delivery import deliver_kyc_submitted
            deliver_kyc_submitted(user_id=user_id, kyc_record_id=kyc_record_id)
            return {"status": "delivered", "kyc_record_id": kyc_record_id}
        except Exception as e:
            logger.error(f"KYC submitted notification failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}


@shared_task(
    name="notifications.notify_kyc_approved",
)
def notify_kyc_approved_task(user_id: int, kyc_record_id: int) -> dict:
    """
    Fan out KYC *approval* notifications (submitter + review team) off the
    request thread. Enqueued by dispatch_notification when a worker is present.
    """
    app = _get_task_flask_app()
    with app.app_context():
        try:
            from app.notifications.delivery import deliver_kyc_approved
            deliver_kyc_approved(user_id=user_id, kyc_record_id=kyc_record_id)
            return {"status": "delivered", "kyc_record_id": kyc_record_id}
        except Exception as e:
            logger.error(f"KYC approved notification failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}


@shared_task(
    name="notifications.schedule_reminders",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def schedule_reminders_task(self, batch_size: int = 25) -> dict:
    """
    Dispatch a bounded page of due notifications.

    Each delivery updates the original scheduled row in place. Unprocessed
    rows remain pending for the next Beat tick; queued delivery messages expire
    if the worker cannot reach them before the next tick.
    """
    batch_size = max(1, min(int(batch_size), 100))
    import time
    t_start = time.perf_counter()
    app = _get_task_flask_app()
    t_app = time.perf_counter()
    with app.app_context():
        try:
            now = datetime.now(timezone.utc)
            # Only re-dispatch rows whose previous broker message had time to
            # expire. Updating last_attempt_at after a successful publish moves
            # those rows behind never-dispatched reminders, preventing the same
            # first page from starving later rows when the worker is busy.
            retry_cutoff = now - timedelta(seconds=55)
            pending = (
                Notification.query.filter(
                    Notification.scheduled_for <= now,
                    Notification.status == NotificationStatus.PENDING,
                    db.or_(
                        Notification.last_attempt_at.is_(None),
                        Notification.last_attempt_at <= retry_cutoff,
                    ),
                )
                .order_by(
                    Notification.last_attempt_at.asc().nullsfirst(),
                    Notification.scheduled_for.asc(),
                    Notification.id.asc(),
                )
                .limit(batch_size)
                .all()
            )
            t_query = time.perf_counter()

            dispatched = 0
            t_dispatch_start = time.perf_counter()
            for notification in pending:
                try:
                    send_notification_task.apply_async(
                        args=(notification.id,),
                        expires=55,
                    )
                    notification.last_attempt_at = now
                    dispatched += 1
                except Exception as e:
                    logger.error(f"Failed to dispatch reminder {notification.id}: {e}")
            t_dispatch = time.perf_counter()

            if dispatched:
                db.session.commit()
            t_commit = time.perf_counter()

            continuation_queued = False
            if len(pending) >= batch_size:
                try:
                    # Continue in another small task so a large reminder set
                    # does not occupy the worker in one long invocation.
                    self.apply_async(
                        kwargs={"batch_size": batch_size},
                        countdown=5,
                    )
                    continuation_queued = True
                except Exception:
                    logger.exception(
                        "Could not schedule the next scheduled-reminder batch"
                    )

            t_end = time.perf_counter()
            logger.info(
                f"Dispatched {dispatched} scheduled reminders out of {len(pending)} eligible "
                f"[timing: total={t_end-t_start:.3f}s app_init={t_app-t_start:.3f}s "
                f"query={t_query-t_app:.3f}s dispatch={t_dispatch-t_dispatch_start:.3f}s "
                f"commit={t_commit-t_dispatch:.3f}s]"
            )
            return {
                "dispatched": dispatched,
                "pending": len(pending),
                "batch_size": batch_size,
                "continuation_queued": continuation_queued,
                "timing": {
                    "total": round(t_end - t_start, 3),
                    "app_init": round(t_app - t_start, 3),
                    "query": round(t_query - t_app, 3),
                    "dispatch": round(t_dispatch - t_dispatch_start, 3),
                    "commit": round(t_commit - t_dispatch, 3),
                }
            }
        except SQLAlchemyError as e:
            logger.error(f"DB error in schedule_reminders: {e}")
            self.retry(exc=e, countdown=60)
            return {"status": "error", "error": str(e)}


@shared_task(
    name="notifications.cleanup_old",
    bind=True,
)
def cleanup_old_notifications_task(
    self,
    days: int = 30,
    batch_size: int = 100,
) -> dict:
    """
    Celery Beat task: archives notification logs older than `days` days
    and soft-deletes old read notifications.
    """
    batch_size = max(1, min(int(batch_size), 500))
    app = _get_task_flask_app()
    with app.app_context():
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Soft-delete one stable page of old read notifications.
            old_read = (
                Notification.query.filter(
                    Notification.is_read == True,
                    Notification.read_at < cutoff,
                    Notification.is_deleted == False,
                )
                .order_by(Notification.id.asc())
                .limit(batch_size)
                .all()
            )
            soft_deleted = len(old_read)
            for notification in old_read:
                notification.soft_delete()

            # Delete old notification logs
            from app.notifications.models import NotificationLog
            old_logs = (
                NotificationLog.query.filter(
                    NotificationLog.attempted_at < cutoff,
                )
                .order_by(NotificationLog.id.asc())
                .limit(batch_size)
                .all()
            )
            log_count = len(old_logs)
            for log in old_logs:
                db.session.delete(log)

            if soft_deleted > 0 or log_count > 0:
                db.session.commit()

            logger.info(
                f"Cleanup batch complete: soft_deleted={soft_deleted}, "
                f"logs_deleted={log_count}"
            )

            continuation_queued = (
                len(old_read) >= batch_size or len(old_logs) >= batch_size
            )
            if continuation_queued:
                try:
                    self.apply_async(
                        kwargs={"days": days, "batch_size": batch_size},
                        countdown=5,
                    )
                except Exception:
                    logger.exception("Could not schedule the next notification-cleanup batch")
                    continuation_queued = False

            return {
                "soft_deleted": soft_deleted,
                "logs_deleted": log_count,
                "batch_size": batch_size,
                "continuation_queued": continuation_queued,
            }
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
    app = _get_task_flask_app()
    with app.app_context():
        try:
            count = NotificationService.resend_failed(max_retries=max_retries, limit=10)
            logger.info(f"Resent {count} failed notifications")
            return {"resent": count}
        except Exception as e:
            logger.error(f"Failed to resend notifications: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

@shared_task(
    name="notifications.send_email_test",
)
@with_flask_app_context
def send_email_test_task(recipient: str, requested_by_user_id: int = None) -> dict:
    """Perform one real SMTP delivery from the asynchronous worker.

    The task's Celery base and this direct-call decorator share the same lazily
    cached Flask app context. No per-message app instance is constructed.
    Results and logs contain only safe status/error codes.
    """
    from types import SimpleNamespace

    from app.notifications.channel_handlers.email import EmailHandler
    from app.utils.security import validate_email

    if not validate_email(str(recipient or "")):
        return {"status": "failed", "error_code": "invalid_recipient"}

    notification = SimpleNamespace(
        id=None,
        type="system_alert",
        subject="AFCON360 email delivery test",
        body=(
            "This is a test message sent through the AFCON360 Owner-managed "
            "email provider using the asynchronous worker."
        ),
        context={"purpose": "owner_email_configuration_test"},
        link=None,
        user_id=requested_by_user_id,
        email=recipient,
    )
    result = EmailHandler().deliver(
        notification,
        {"email": recipient, "user_id": requested_by_user_id},
    )
    if result.get("success"):
        logger.info("Asynchronous email configuration test was accepted by the provider")
        return {"status": "accepted", "error_code": None}
    logger.warning(
        "Asynchronous email configuration test failed (error_code=%s)",
        result.get("error_code", "email_delivery_failed"),
    )
    return {
        "status": "failed",
        "error_code": result.get("error_code", "email_delivery_failed"),
    }
