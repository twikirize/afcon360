"""Central redaction for application log records.

The filter runs at LogRecord creation time so it also covers loggers that set
propagate=False (Flask, Werkzeug, Celery and module-specific loggers).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import traceback
from collections.abc import Mapping

_REDACTED = "[REDACTED]"
_SENSITIVE_NAME = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|"
    r"access[_-]?key|client[_-]?secret|auth(?:orization)?|credential|"
    r"encryption[_-]?key|signing[_-]?key|account[_-]?sid|"
    r"security[_-]?salt|dsn|webhook[_-]?url|"
    r"africa[_-]?talking[_-]?username|"
    r"(?:smtp|mail)[_-]?(?:user(?:name)?|pass(?:word)?))",
    re.IGNORECASE,
)
_ASSIGNMENT = re.compile(
    r"(?i)(?P<prefix>[\"']?(?:[a-z0-9_.-]*(?:password|passwd|secret|token|"
    r"api[_-]?key|private[_-]?key|access[_-]?key|client[_-]?secret|"
    r"authorization|credential|encryption[_-]?key|account[_-]?sid|"
    r"security[_-]?salt|dsn|webhook[_-]?url|"
    r"africa[_-]?talking[_-]?username|"
    r"(?:smtp|mail)[_-]?(?:user(?:name)?|pass(?:word)?))"
    r"[a-z0-9_.-]*)[\"']?\s*[:=]\s*[\"']?)"
    r"(?P<value>[^\s,\"';&}\]]+)"
)
_BEARER = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")
_BASIC = re.compile(r"(?i)(\bBasic\s+)[A-Za-z0-9+/=]+")
_URL_PASSWORD = re.compile(r"(://[^:/\s@]+:)[^@/\s]+(@)")
_SECRET_VALUES: set[str] = set()
_LOCK = threading.RLock()
_INSTALLED = False
_STANDARD_RECORD_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName",
}


def is_sensitive_name(name: object) -> bool:
    return bool(_SENSITIVE_NAME.search(str(name or "")))


def register_secret(value: object) -> None:
    """Register a literal secret so unlabelled exception text is also scrubbed."""
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return
    candidate = str(value)
    # Ignore empty and very short values: replacing them causes false positives.
    if len(candidate) < 4 or candidate.lower() in {"none", "null", "true", "false"}:
        return
    with _LOCK:
        _SECRET_VALUES.add(candidate)


def register_secret_mapping(value: object) -> None:
    """Register values beneath secret-named keys, recursively."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if is_sensitive_name(key):
                if isinstance(item, (dict, list, tuple)):
                    register_secret_mapping(item)
                else:
                    register_secret(item)
            else:
                register_secret_mapping(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            register_secret_mapping(item)


def register_environment_secrets(environ=None) -> None:
    values = os.environ if environ is None else environ
    for key, value in values.items():
        if is_sensitive_name(key):
            register_secret(value)
        # Connection strings may embed a password even though the variable name
        # itself is not always password-like (DATABASE_URL, REDIS_URL, broker URL).
        if str(key).upper() in {
            "DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "REDIS_URL",
            "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND",
        }:
            register_secret(value)


def redact_text(value: object) -> str:
    text = str(value)
    with _LOCK:
        secrets = sorted(_SECRET_VALUES, key=len, reverse=True)
    for secret in secrets:
        text = text.replace(secret, _REDACTED)
    text = _ASSIGNMENT.sub(lambda match: match.group("prefix") + _REDACTED, text)
    text = _BEARER.sub(r"\1" + _REDACTED, text)
    text = _BASIC.sub(r"\1" + _REDACTED, text)
    text = _URL_PASSWORD.sub(r"\1" + _REDACTED + r"\2", text)
    return text


def _sanitize_extra(value):
    """Recursively scrub nested structured logging fields."""
    if isinstance(value, Mapping):
        return {
            key: _REDACTED if is_sensitive_name(key) else _sanitize_extra(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_extra(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _sanitize_record(record: logging.LogRecord) -> logging.LogRecord:
    try:
        message = record.getMessage()
    except Exception:
        message = "<log message unavailable>"
    record.msg = redact_text(message)
    record.args = ()

    if record.exc_info:
        try:
            record.exc_text = redact_text(
                "".join(traceback.format_exception(*record.exc_info))
            )
        except Exception:
            record.exc_text = "[REDACTED exception details]"
        record.exc_info = None

    if record.exc_text:
        record.exc_text = redact_text(record.exc_text)
    if record.stack_info:
        record.stack_info = redact_text(record.stack_info)

    # Sanitize custom extra fields as well as the rendered message.
    for key, value in tuple(record.__dict__.items()):
        if key in _STANDARD_RECORD_FIELDS:
            continue
        record.__dict__[key] = (
            _REDACTED if is_sensitive_name(key) else _sanitize_extra(value)
        )
    return record


def install_log_redaction() -> None:
    """Install redaction for both record creation and post-factory extras."""
    global _INSTALLED

    # logging.LogRecordFactory runs before Logger.makeRecord attaches `extra`
    # fields. Wrap makeRecord as well so structured secrets are scrubbed before
    # the record reaches any handler (including non-propagating loggers).
    with _LOCK:
        if not getattr(logging.Logger.makeRecord, "_afcon360_redacting_make_record", False):
            previous_make_record = logging.Logger.makeRecord

            def redacting_make_record(self, *args, **kwargs):
                record = previous_make_record(self, *args, **kwargs)
                return _sanitize_record(record)

            redacting_make_record._afcon360_redacting_make_record = True
            logging.Logger.makeRecord = redacting_make_record

    if _INSTALLED:
        return
    with _LOCK:
        if _INSTALLED:
            return
        previous_factory = logging.getLogRecordFactory()

        def redacting_factory(*args, **kwargs):
            return _sanitize_record(previous_factory(*args, **kwargs))

        redacting_factory._afcon360_redacting_factory = True
        logging.setLogRecordFactory(redacting_factory)
        _INSTALLED = True


install_log_redaction()
