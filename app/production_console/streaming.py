"""
Production Console Log Streaming Service.

Captures structured log events, sanitizes sensitive data, stores bounded history in Redis,
and broadcasts live to authorized Owner/Super Admin consoles via Flask-SocketIO.
"""
import logging
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from collections import deque

from flask import has_request_context, request
from app.extensions import redis_client, socketio
from app.notifications.events.context import get_correlation_id

logger = logging.getLogger(__name__)

MAX_HISTORY = 2000
HISTORY_KEY = "prod_console:history"
SENSITIVE_PATTERNS = [
    (re.compile(r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']?[^"\'\s]+'), r'\1=***'),
    (re.compile(r'(?i)(api[_-]?key|apikey|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*["\']?[^"\'\s]+'), r'\1=***'),
    (re.compile(r'(?i)(redis[_-]?url|database[_-]?url|db[_-]?url)\s*[:=]\s*["\']?[^"\'\s]+'), r'\1=***'),
    (re.compile(r'(?i)(encryption[_-]?key|secret[_-]?salt|jwt[_-]?secret)\s*[:=]\s*["\']?[^"\'\s]+'), r'\1=***'),
    (re.compile(r'(?i)(card[_-]?number|cc[_-]?number|pan)\s*[:=]\s*["\']?[^"\'\s]+'), r'\1=***'),
    (re.compile(r'(?i)(cvv|cvc|pin)\s*[:=]\s*["\']?[^"\'\s]+'), r'\1=***'),
    (re.compile(r'redis://[^@\s:]+:[^@\s]+@'), 'redis://:***@'),
    (re.compile(r'postgresql://[^@\s:]+:[^@\s]+@'), 'postgresql://:***@'),
    (re.compile(r'mysql://[^@\s:]+:[^@\s]+@'), 'mysql://:***@'),
    (re.compile(r'Bearer\s+[A-Za-z0-9\-\._~+/]+=*'), 'Bearer ***'),
    (re.compile(r'eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+'), 'eyJ***'),
]

CATEGORY_PATTERNS = {
    'HTTP': [r'werkzeug', r'flask\.app', r'HTTP', r'\d{3}\s+\w+\s+/'],
    'DATABASE': [r'sqlalchemy', r'psycopg', r'postgresql', r'DATABASE', r'IntegrityError', r'OperationalError'],
    'SECURITY': [r'auth', r'login', r'csrf', r'permission', r'authorization', r'forbidden', r'unauthorized', r'rate.?limit'],
    'PAYMENT': [r'payment', r'wallet', r'transaction', r'flutterwave', r'paystack', r'stripe', r'paypal', r'webhook'],
    'WALLET': [r'wallet', r'ledger', r'balance', r'account', r'deposit', r'withdraw', r'transfer'],
    'CELERY': [r'celery', r'task', r'worker', r'beat', r'retry', r'queue'],
    'REDIS': [r'redis', r'connection.?pool', r'cache'],
    'AUTH': [r'auth', r'login', r'logout', r'session', r'impersonat', r'mfa', r'2fa'],
    'EVENTS': [r'event', r'ticket', r'registration'],
    'ACCOMMODATION': [r'accommodation', r'booking', r'property', r'reservation', r'host'],
    'TRANSPORT': [r'transport', r'vehicle', r'driver', r'route'],
    'NOTIFICATIONS': [r'notification', r'email', r'sms', r'push', r'webhook'],
}


def sanitize_message(message: str) -> str:
    """Remove sensitive data from log messages."""
    if not message:
        return message
    
    sanitized = message
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def categorize_log(logger_name: str, message: str) -> str:
    """Categorize log entry based on logger name and message content."""
    combined = f"{logger_name} {message}".lower()
    
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                return category
    return 'GENERAL'


def get_severity_level(record: logging.LogRecord) -> str:
    """Get severity level from log record."""
    return record.levelname


def extract_http_info(record: logging.LogRecord) -> Optional[Dict[str, Any]]:
    """Extract HTTP request info if available."""
    if not has_request_context():
        return None
    
    return {
        'method': request.method,
        'path': request.path,
        'endpoint': request.endpoint,
        'status_code': getattr(record, 'status_code', None),
        'remote_addr': request.remote_addr,
        'user_agent': request.user_agent.string if request.user_agent else None,
    }


def extract_exception_info(record: logging.LogRecord) -> Optional[Dict[str, Any]]:
    """Extract exception/traceback info if present."""
    if not record.exc_info:
        return None
    
    exc_type, exc_value, exc_tb = record.exc_info
    import traceback
    
    return {
        'exception_type': exc_type.__name__ if exc_type else None,
        'exception_message': str(exc_value) if exc_value else None,
        'traceback': ''.join(traceback.format_exception(exc_type, exc_value, exc_tb)) if exc_tb else None,
    }


class ProductionConsoleHandler(logging.Handler):
    """
    Custom logging handler that:
    1. Sanitizes log messages
    2. Stores bounded history in Redis
    3. Broadcasts live to SocketIO clients
    """
    
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self._local_history = deque(maxlen=100)
    
    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self._should_skip(record):
                return
            
            event = self._build_event(record)
            self._store_history(event)
            self._broadcast_live(event)
            
        except Exception:
            self.handleError(record)
    
    def _should_skip(self, record: logging.LogRecord) -> bool:
        """Skip internal/health check logs to reduce noise."""
        skip_loggers = [
            'werkzeug',
            'socketio',
            'engineio',
            'flask_socketio',
        ]
        
        if record.name in skip_loggers:
            return True
        
        if record.name.startswith('urllib3') or record.name.startswith('requests'):
            return True
        
        if record.levelno < logging.DEBUG:
            return True
        
        if hasattr(record, 'prod_console_skip') and getattr(record, 'prod_console_skip', False):  # type: ignore[attr-defined]
            return True
        
        return False
    
    def _build_event(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Build structured log event from record."""
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc)
        
        message = record.getMessage()
        sanitized_message = sanitize_message(message)
        
        event = {
            'id': f"evt_{uuid.uuid4().hex[:12]}",
            'timestamp': timestamp.isoformat(),
            'timestamp_display': timestamp.strftime('%H:%M:%S'),
            'severity': record.levelname,
            'logger': record.name,
            'message': sanitized_message,
            'category': categorize_log(record.name, message),
            'correlation_id': get_correlation_id(create=False),
        }
        
        http_info = extract_http_info(record)
        if http_info:
            event['http'] = http_info
        
        exception_info = extract_exception_info(record)
        if exception_info:
            event['exception'] = exception_info
        
        if hasattr(record, 'correlation_id'):
            event['correlation_id'] = getattr(record, 'correlation_id', None)  # type: ignore[attr-defined]
        
        if hasattr(record, 'task_id'):
            event['task_id'] = getattr(record, 'task_id', None)  # type: ignore[attr-defined]
        
        if hasattr(record, 'task_name'):
            event['task_name'] = getattr(record, 'task_name', None)  # type: ignore[attr-defined]
        
        return event
    
    def _store_history(self, event: Dict[str, Any]) -> None:
        """Store event in Redis bounded history."""
        try:
            if not redis_client._url:
                return
            
            client = redis_client.client
            if not client:
                return
            
            event_json = json.dumps(event, default=str)
            
            pipe = client.pipeline()
            pipe.lpush(HISTORY_KEY, event_json)
            pipe.ltrim(HISTORY_KEY, 0, MAX_HISTORY - 1)
            pipe.execute()
            
        except Exception as e:
            logger.debug(f"Failed to store console history: {e}")
    
    def _broadcast_live(self, event: Dict[str, Any]) -> None:
        """Broadcast event to connected SocketIO clients."""
        try:
            socketio.emit('console_event', event, namespace='/console')
        except Exception as e:
            logger.debug(f"Failed to broadcast console event: {e}")
    
    @classmethod
    def get_recent_history(cls, limit: int = 500) -> List[Dict[str, Any]]:
        """Get recent history from Redis."""
        try:
            if not redis_client._url:
                return []
            
            client = redis_client.client
            if not client:
                return []
            
            events = client.lrange(HISTORY_KEY, 0, limit - 1)
            # Handle both sync and async redis clients
            if hasattr(events, '__await__'):
                # Async client - can't use in sync context
                return []
            if not events:
                return []
            return [json.loads(e) for e in events]
            
        except Exception as e:
            logger.debug(f"Failed to get console history: {e}")
            return []
    
    @classmethod
    def log_event(cls, event: Dict[str, Any]) -> None:
        """Store event in history and broadcast to connected SocketIO clients."""
        try:
            cls._store_history(event)
        except Exception:
            pass
        try:
            socketio.emit('console_event', event, namespace='/console')
        except Exception:
            pass

    @classmethod
    def clear_history(cls) -> bool:
        """Clear console history."""
        try:
            if not redis_client._url:
                return True
            
            client = redis_client.client
            if not client:
                return True
            
            client.delete(HISTORY_KEY)
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear console history: {e}")
            return False


class FrontendEventCapture:
    """Capture frontend events (clicks, navigation, performance, errors)."""
    
    @staticmethod
    def capture(data: Dict[str, Any]) -> None:
        timestamp = datetime.now(timezone.utc)
        event = {
            'id': f"evt_{uuid.uuid4().hex[:12]}",
            'timestamp': timestamp.isoformat(),
            'timestamp_display': timestamp.strftime('%H:%M:%S'),
            'severity': data.get('severity', 'INFO'),
            'logger': data.get('logger', 'frontend.console'),
            'message': sanitize_message(data.get('message', '')),
            'category': data.get('category', 'FRONTEND'),
            'correlation_id': data.get('correlation_id'),
            'frontend': data.get('frontend', {}),
        }
        ProductionConsoleHandler.log_event(event)


class CeleryEventCapture:
    """Capture Celery task events for the production console."""
    
    @staticmethod
    def task_started(task_id: str, task_name: str, args: tuple = None, kwargs: dict = None) -> logging.LogRecord:
        record = logging.LogRecord(
            name='celery.task',
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg=f"Task started: {task_name}",
            args=(),
            exc_info=None,
        )
        record.task_id = task_id  # type: ignore[attr-defined]
        record.task_name = task_name  # type: ignore[attr-defined]
        record.prod_console_skip = False  # type: ignore[attr-defined]
        return record
    
    @staticmethod
    def task_succeeded(task_id: str, task_name: str, result: Any = None) -> logging.LogRecord:
        record = logging.LogRecord(
            name='celery.task',
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg=f"Task succeeded: {task_name}",
            args=(),
            exc_info=None,
        )
        record.task_id = task_id  # type: ignore[attr-defined]
        record.task_name = task_name  # type: ignore[attr-defined]
        record.prod_console_skip = False  # type: ignore[attr-defined]
        return record
    
    @staticmethod
    def task_failed(task_id: str, task_name: str, exception: Exception, traceback_str: str = None) -> logging.LogRecord:
        record = logging.LogRecord(
            name='celery.task',
            level=logging.ERROR,
            pathname='',
            lineno=0,
            msg=f"Task failed: {task_name}: {exception}",
            args=(),
            exc_info=(type(exception), exception, exception.__traceback__),
        )
        record.task_id = task_id  # type: ignore[attr-defined]
        record.task_name = task_name  # type: ignore[attr-defined]
        record.prod_console_skip = False  # type: ignore[attr-defined]
        return record
    
    @staticmethod
    def task_retried(task_id: str, task_name: str, exception: Exception, retries: int) -> logging.LogRecord:
        record = logging.LogRecord(
            name='celery.task',
            level=logging.WARNING,
            pathname='',
            lineno=0,
            msg=f"Task retry {retries}: {task_name}: {exception}",
            args=(),
            exc_info=None,
        )
        record.task_id = task_id  # type: ignore[attr-defined]
        record.task_name = task_name  # type: ignore[attr-defined]
        record.prod_console_skip = False  # type: ignore[attr-defined]
        return record
    
    @staticmethod
    def worker_online(worker_name: str) -> logging.LogRecord:
        record = logging.LogRecord(
            name='celery.worker',
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg=f"Worker online: {worker_name}",
            args=(),
            exc_info=None,
        )
        record.prod_console_skip = False
        return record
    
    @staticmethod
    def worker_offline(worker_name: str):
        record = logging.LogRecord(
            name='celery.worker',
            level=logging.WARNING,
            pathname='',
            lineno=0,
            msg=f"Worker offline: {worker_name}",
            args=(),
            exc_info=None,
        )
        record.prod_console_skip = False
        return record


def init_production_console_logging(app):
    """Initialize production console logging handler."""
    handler = ProductionConsoleHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    app.logger.info("Production console logging initialized")
    return handler