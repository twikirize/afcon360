"""
app/celery_app.py

Celery application factory for AFCON360.
Works unmodified on Windows (dev), and Linux (Oracle Cloud / AWS / any prod host).

Pool selection is automatic based on platform, with an env-var override
for edge cases (WSL, Docker-on-Windows, CI runners, etc).

Start workers:
    celery -A app.celery_app worker --loglevel=info

Start beat scheduler (runs periodic tasks):
    celery -A app.celery_app beat --loglevel=info

Or combined (dev only - not for production):
    celery -A app.celery_app worker --beat --loglevel=info

Override pool/concurrency without touching code:
    set CELERY_WORKER_POOL=threads          (Windows)
    export CELERY_WORKER_POOL=prefork       (Linux/macOS)
    export CELERY_WORKER_CONCURRENCY=8
"""

import os
import sys

from celery import Celery


def _default_pool() -> str:
    """
    Windows can't fork worker processes, so Celery's default 'prefork'
    pool always fails there with PermissionError/OSError from billiard.
    Linux and macOS fork fine, so prefork is the right (fast) default there.

    This function picks the correct default per-platform automatically,
    so the SAME codebase works on your Windows dev machine and on
    Oracle/AWS Linux prod without any manual flags or code changes.
    """
    if os.environ.get("CELERY_WORKER_POOL"):
        return os.environ["CELERY_WORKER_POOL"]

    if sys.platform == "win32":
        # 'solo' is the most reliable on Windows. 'threads' gives you
        # actual concurrency for I/O-bound tasks (webhooks, media processing)
        # and is generally safe too - use it as the Windows default.
        return "threads"

    return "prefork"


def _default_concurrency(pool: str) -> int | None:
    if os.environ.get("CELERY_WORKER_CONCURRENCY"):
        return int(os.environ["CELERY_WORKER_CONCURRENCY"])
    if pool == "solo":
        return 1
    if pool == "threads":
        return 8  # I/O-bound tasks (webhooks, media) benefit from more threads
    return None  # let Celery/prefork pick os.cpu_count()


def make_celery(app=None):
    """
    Create and configure the Celery instance.
    Accepts an optional Flask app for context binding.
    """
    from app.config import Config

    celery = Celery(
        "afcon360",
        broker=Config.CELERY_BROKER_URL,
        backend=Config.CELERY_RESULT_BACKEND,
        include=[
            "app.tasks.webhook_processor",
            "app.tasks.cleanup",
            "app.tasks.accommodation_reminders",
            "app.media.tasks",
            "app.notifications.tasks",
            # add future task modules here
        ],
    )

    pool = _default_pool()
    concurrency = _default_concurrency(pool)

    # Beat schedule - periodic tasks
    celery.conf.beat_schedule = {
        "process-webhook-events": {
            "task": "wallet.process_webhook_events",
            "schedule": 60.0,  # every 60 seconds
        },
        "cleanup-expired-holds": {
            "task": "accommodation.cleanup_expired_holds",
            "schedule": 300.0,  # every 5 minutes
        },
        "accommodation-registration-reminders": {
            "task": "accommodation.send_registration_reminders",
            "schedule": 3600.0,  # every 1 hour
        },
        "accommodation-expire-unapproved-bookings": {
            "task": "accommodation.expire_unapproved_bookings",
            "schedule": 3600.0,  # every 1 hour
        },
        "notifications-schedule-reminders": {
            "task": "notifications.schedule_reminders",
            "schedule": 60.0,  # every 60 seconds
        },
        "notifications-resend-failed": {
            "task": "notifications.resend_failed",
            "schedule": 300.0,  # every 5 minutes
        },
        "notifications-cleanup-old": {
            "task": "notifications.cleanup_old",
            "schedule": 86400.0,  # every 24 hours
        },
    }

    celery.conf.update(
        timezone="UTC",
        enable_utc=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],

        # --- cross-platform worker pool (the actual fix) ---
        worker_pool=pool,
        worker_concurrency=concurrency,
        worker_prefetch_multiplier=1 if pool != "prefork" else 4,

        # --- silences the CPendingDeprecationWarning you saw, and is
        # correct behavior for prod: retry connecting to the broker on
        # startup instead of failing immediately (e.g. Redis not up yet
        # when a container restarts) ---
        broker_connection_retry_on_startup=True,

        # --- sane prod defaults ---
        task_track_started=True,
        task_acks_late=True,
        task_time_limit=30 * 60,
        task_soft_time_limit=25 * 60,
        result_expires=3600,
        worker_max_tasks_per_child=200,  # recycle workers, avoids slow mem creep
    )

    # Bind Flask app context so tasks can use current_app
    if app is not None:
        celery.conf.update(app.config)

        class ContextTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery.Task = ContextTask

    return celery


# Module-level instance for CLI usage:
#   celery -A app.celery_app worker
celery_app = make_celery()