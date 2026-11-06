"""
app/utils/async_fallback.py

General-purpose async execution with Celery -> Thread -> Inline fallback.

Use this when you want to run something asynchronously but gracefully
degrade if Celery/Redis is unavailable. DB must be working.
"""

import threading
import time
from functools import wraps
from typing import Callable, Any, Optional, Dict

from flask import current_app


# Cache worker availability to avoid repeated broker pings
_WORKER_TTL_SECONDS = 15.0
_worker_state = {"checked_at": 0.0, "available": False}


def celery_worker_available(force: bool = False) -> bool:
    """
    Return True when at least one Celery worker answers a broker ping.
    
    Failures (broker unreachable, no workers registered) are treated as
    "unavailable" so the caller falls back to the in-process thread path.
    Cached for 15 seconds to avoid overhead.
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
        pass

    _worker_state["checked_at"] = now
    _worker_state["available"] = available
    return available


def _run_in_thread(target_fn: Callable, app, *args, **kwargs):
    """Run target_fn(*args, **kwargs) in a daemon thread with its own app context."""
    def _target():
        with app.app_context():
            try:
                target_fn(*args, **kwargs)
            except Exception:
                import logging
                logger = logging.getLogger(__name__)
                logger.error("Async fallback execution failed", exc_info=True)
            finally:
                try:
                    from app.extensions import db
                    db.session.remove()
                except Exception:
                    pass

    threading.Thread(target=_target, name="async-fallback", daemon=True).start()


def with_app_context(fn: Callable) -> Callable:
    """
    Decorator: run fn inside Flask app context.
    
    Reuses current_app if already in context (tests, inline calls),
    otherwise creates app defensively. Mirrors _with_app_context pattern.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            from flask import current_app
            if current_app:
                return fn(*args, **kwargs)
        except Exception:
            pass

        from app import create_app
        app = create_app()
        with app.app_context():
            return fn(*args, **kwargs)

    return wrapper


def run_async(
    target_fn: Callable,
    *args,
    celery_task: Optional[Callable] = None,
    **kwargs
) -> Any:
    """
    Execute target_fn asynchronously with fallback chain:
    
    1. If celery_task provided AND worker available -> celery_task.delay(*args, **kwargs)
    2. Else -> background thread with app context
    3. If app.testing -> run inline (synchronous)
    
    Returns:
        - Celery AsyncResult if enqueued
        - None if thread/inline (fire-and-forget)
    
    Usage:
        from app.utils.async_fallback import run_async
        
        def my_work(user_id, action):
            # ... do work ...
            pass
        
        # With Celery task (preferred)
        from app.tasks.my_tasks import my_celery_task
        run_async(my_work, user_id, action, celery_task=my_celery_task)
        
        # Without Celery task (pure fallback)
        run_async(my_work, user_id, action)
    """
    # Testing: keep synchronous so assertions don't race
    try:
        if current_app and current_app.testing:
            return target_fn(*args, **kwargs)
    except Exception:
        pass

    # Try Celery first
    if celery_task is not None and celery_worker_available():
        try:
            return celery_task.delay(*args, **kwargs)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Celery enqueue failed; falling back to background thread",
                exc_info=True,
            )

    # Fallback: background thread with app context
    try:
        app = current_app._get_current_object()
    except RuntimeError:
        # No current app context (e.g., called from non-request thread)
        from app import create_app
        app = create_app()

    _run_in_thread(target_fn, app, *args, **kwargs)
    return None


def run_async_with_result(
    target_fn: Callable,
    *args,
    celery_task: Optional[Callable] = None,
    **kwargs
) -> Any:
    """
    Execute target_fn and return its result (not fire-and-forget).
    
    Fallback chain:
    1. Celery task (if available) -> returns AsyncResult
    2. Inline execution -> returns actual result
    
    Use when caller needs the result (not just fire-and-forget).
    """
    # Testing: keep synchronous
    try:
        if current_app and current_app.testing:
            return target_fn(*args, **kwargs)
    except Exception:
        pass

    if celery_task is not None and celery_worker_available():
        try:
            return celery_task.delay(*args, **kwargs)
        except Exception:
            pass

    # Inline fallback (blocking)
    try:
        return target_fn(*args, **kwargs)
    except Exception:
        import logging
        logging.getLogger(__name__).error("Inline fallback execution failed", exc_info=True)
        raise


class AsyncFallback:
    """
    Class-based API for cleaner usage with configuration.
    
    Usage:
        fallback = AsyncFallback(celery_task=my_celery_task)
        fallback.fire_and_forget(my_func, arg1, arg2)
        result = fallback.with_result(my_func, arg1, arg2)
    """
    
    def __init__(self, celery_task: Optional[Callable] = None):
        self.celery_task = celery_task
    
    def fire_and_forget(self, target_fn: Callable, *args, **kwargs) -> Any:
        return run_async(target_fn, *args, celery_task=self.celery_task, **kwargs)
    
    def with_result(self, target_fn: Callable, *args, **kwargs) -> Any:
        return run_async_with_result(target_fn, *args, celery_task=self.celery_task, **kwargs)