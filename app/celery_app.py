"""
app/celery_app.py

Celery application factory for AFCON360.

Start workers:
    celery -A app.celery_app worker --loglevel=info

Start beat scheduler (runs periodic tasks):
    celery -A app.celery_app beat --loglevel=info

Or combined (dev only - not for production):
    celery -A app.celery_app worker --beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab


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
            # add future task modules here
        ]
    )

    # Beat schedule - periodic tasks
    celery.conf.beat_schedule = {
        # Process queued/failed webhook events every 60 seconds
        "process-webhook-events": {
            "task": "wallet.process_webhook_events",
            "schedule": 60.0,  # every 60 seconds
        },
    }

    celery.conf.timezone = "UTC"
    celery.conf.task_serializer = "json"
    celery.conf.result_serializer = "json"
    celery.conf.accept_content = ["json"]

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