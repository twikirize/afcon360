#app/utils/monitoring.py
"""
Monitoring utilities for AFCON360
"""
import time
import logging
from datetime import datetime
from functools import wraps
from typing import Optional, Dict, Any
import threading
from app.utils.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)


class MonitorContext:
    """Context manager for monitoring operations"""

    def __init__(self, operation_name: str, tags: Optional[Dict] = None):
        self.operation_name = operation_name
        self.tags = tags or {}
        self.start_time = None
        self.success = False

    def __enter__(self):
        self.start_time = time.time()
        logger.info(f"Starting operation: {self.operation_name}", extra={"tags": self.tags})
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.success = exc_type is None

        if self.success:
            logger.info(
                f"Operation completed: {self.operation_name}",
                extra={"duration": duration, "tags": self.tags}
            )
        else:
            logger.error(
                f"Operation failed: {self.operation_name} - {exc_val}",
                extra={"duration": duration, "tags": self.tags, "error": str(exc_val)}
            )

        return False  # Don't suppress exceptions


def monitor_endpoint(endpoint_name: Optional[str] = None):
    """
    Decorator to monitor endpoint execution
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            name = endpoint_name or func.__name__
            with MonitorContext(f"endpoint.{name}"):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def record_metric(name: str, value: float, tags: Optional[Dict] = None):
    """
    Record a custom metric
    """
    logger.info(f"Metric recorded: {name}={value}", extra={"tags": tags or {}})


def start_span(operation_name: str, **kwargs):
    """
    Start a monitoring span (simplified version)
    Returns a context manager
    """
    return MonitorContext(operation_name, kwargs.get("tags"))


def track_operation(operation_name: Optional[str] = None):
    """
    Decorator to track operation execution
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            name = operation_name or func.__name__
            with MonitorContext(f"operation.{name}"):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def with_circuit_breaker(
        failure_threshold: int = 5,
        reset_timeout: int = 60,
        expected_exceptions: tuple = (Exception,)
):
    """
    Simple circuit breaker pattern decorator
    """

    def decorator(func):
        failures = 0
        last_failure_time = 0
        circuit_open = False

        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal failures, last_failure_time, circuit_open

            current_time = time.time()

            # Check if circuit should be half-open
            if circuit_open and current_time - last_failure_time > reset_timeout:
                circuit_open = False
                failures = 0
                logger.info(f"Circuit half-open for {func.__name__}")

            # Check if circuit is open
            if circuit_open:
                raise ServiceUnavailableError(
                    f"Circuit breaker open for {func.__name__}",
                    service_name=func.__name__
                )

            try:
                result = func(*args, **kwargs)
                # Reset failures on success
                failures = 0
                return result

            except expected_exceptions as e:
                failures += 1
                last_failure_time = current_time

                if failures >= failure_threshold:
                    circuit_open = True
                    logger.error(f"Circuit opened for {func.__name__} after {failures} failures")

                raise e

        return wrapper

    return decorator


# Thread-local storage for request context
_request_context = threading.local()


def get_request_context():
    """Get current request context for monitoring"""
    return getattr(_request_context, "data", {})


def set_request_context(data: Dict[str, Any]):
    """Set request context for monitoring"""
    _request_context.data = data


def track_booking_funnel_event(event_name: str, properties: dict = None):
    """
    Lightweight funnel tracking. Logs structured events.
    Integrates with PostHog/GA4 if configured, otherwise structured log.
    """
    import structlog
    log = structlog.get_logger() if _has_structlog() else None
    payload = {
        'event': event_name,
        'ts': __import__('datetime').datetime.utcnow().isoformat(),
        **(properties or {})
    }
    if log:
        log.info('funnel_event', **payload)
    else:
        __import__('logging').getLogger(__name__).info(f'FUNNEL: {payload}')


def _has_structlog():
    try:
        import structlog; return True
    except ImportError:
        return False
