"""
AFCON360 Async Notification Dispatch

Large notification fan-outs (notably the admin review team) must not run on the
request thread: a single SMTP delivery takes seconds and a fan-out to ~18 admins
blocks the HTTP response for well over a minute (observed: KYC submit 78s,
KYC approve ~50s).

Hybrid delivery strategy — chosen by runtime capability, not by environment:

  * A Celery worker answers a broker ping  -> enqueue the registered Celery task.
  * No worker answers                      -> run delivery in a daemon thread
                                              that owns its own app context and
                                              DB session.
  * Tests (``app.testing``)                -> run inline so assertions remain
                                              deterministic.

Rationale: forwarding to Celery requires a live worker that consumes the
``notifications.*`` (bulk) queue; otherwise queued tasks would never run and
notifications would be silently dropped. When no such worker is present, the
background-thread fallback still delivers while keeping the HTTP response fast.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

# A broker ping is a broadcast round-trip (~0.5s when no worker answers). Cache
# the verdict briefly so the cost is not paid on every notification.
_WORKER_TTL_SECONDS = 15.0
_worker_state = {"checked_at": 0.0, "available": False}


def celery_worker_available(force=False):
    """Return True when at least one Celery worker answers a broker ping.

    Failures (broker unreachable, no workers registered) are treated as
    "unavailable" so the caller falls back to the in-process thread path.
    """
    now = time.monotonic()
    if not force and (now - _worker_state["checked_at"]) < _WORKER_TTL_SECONDS:
        return _worker_state["available"]

    available = False
    try:
        from app.celery_app import celery_app
        replies = celery_app.control.ping(timeout=0.5) or []
        available = bool(replies)
    except Exception:
        logger.debug("Celery worker ping failed", exc_info=True)

    _worker_state["checked_at"] = now
    _worker_state["available"] = available
    return available


def _run_in_thread(deliver, app, kwargs):
    """Run ``deliver(**kwargs)`` in a daemon thread with its own app context."""

    def _target():
        with app.app_context():
            try:
                deliver(**kwargs)
            except Exception:
                logger.error("Async notification delivery failed", exc_info=True)
            finally:
                try:
                    from app.extensions import db
                    db.session.remove()
                except Exception:
                    pass

    threading.Thread(target=_target, name="notify-dispatch", daemon=True).start()


def dispatch_notification(deliver, celery_task=None, **kwargs):
    """Deliver a notification off the request thread.

    Args:
        deliver: Plain callable executed in-process (inline under tests, in a
            background thread otherwise). Receives ``**kwargs``.
        celery_task: Optional Celery task enqueued when a worker is available.
            Must accept the same keyword arguments.
        **kwargs: Payload passed to ``deliver`` and/or ``celery_task``.
    """
    from flask import current_app

    app = current_app._get_current_object()

    # Tests: keep delivery synchronous so assertions do not race the dispatcher.
    if app.testing:
        deliver(**kwargs)
        return

    if celery_task is not None and celery_worker_available():
        try:
            celery_task.delay(**kwargs)
            return
        except Exception:
            logger.warning(
                "Celery enqueue failed; falling back to background thread",
                exc_info=True,
            )

    _run_in_thread(deliver, app, kwargs)
