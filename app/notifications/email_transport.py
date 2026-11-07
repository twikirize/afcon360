"""Single shared SMTP transport for web requests and Celery workers."""
from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr
import smtplib
import ssl


class EmailDeliveryError(RuntimeError):
    """Safe provider failure carrying only a non-secret diagnostic code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _format_sender(value):
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return formataddr((str(value[0]), str(value[1])))
    sender = str(value or "").strip()
    if not sender or "@" not in sender:
        raise EmailDeliveryError("missing_or_invalid_sender")
    return sender


def send_smtp_email(*, recipient: str, subject: str, body: str, html: str = None) -> str:
    """Send one message using the active Owner-managed SMTP settings.

    The resolver reads the same PostgreSQL row from web and worker processes.
    Environment settings are used only while no Owner-managed email provider
    row exists. No credentials are logged or returned.
    """
    from app.notifications.settings import CommunicationSettingsService

    config = CommunicationSettingsService.resolve_email_transport_config()
    host = str(config.get("smtp_host") or "").strip()
    try:
        port = int(config.get("smtp_port") or 587)
    except (TypeError, ValueError):
        raise EmailDeliveryError("invalid_smtp_port") from None

    use_tls = _as_bool(config.get("use_tls"), default=True)
    use_ssl = _as_bool(config.get("use_ssl"), default=False)
    username = config.get("smtp_user")
    password = config.get("smtp_pass")

    if not host:
        raise EmailDeliveryError("missing_smtp_host")
    if not 1 <= port <= 65535:
        raise EmailDeliveryError("invalid_smtp_port")
    if use_tls and use_ssl:
        raise EmailDeliveryError("tls_ssl_conflict")
    if bool(username) != bool(password):
        raise EmailDeliveryError("incomplete_smtp_authentication")
    if not recipient or "@" not in recipient:
        raise EmailDeliveryError("invalid_recipient")

    message = EmailMessage()
    message["Subject"] = str(subject or "AFCON360 notification")
    message["From"] = _format_sender(config.get("default_sender"))
    message["To"] = recipient
    message.set_content(str(body or ""))
    if html:
        message.add_alternative(str(html), subtype="html")

    context = ssl.create_default_context()
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(
                host, port, timeout=20, context=context
            ) as connection:
                if username:
                    connection.login(username, password)
                refused = connection.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as connection:
                connection.ehlo()
                if use_tls:
                    connection.starttls(context=context)
                    connection.ehlo()
                if username:
                    connection.login(username, password)
                refused = connection.send_message(message)
    except EmailDeliveryError:
        raise
    except Exception as exc:
        # Exception strings from SMTP libraries/providers are untrusted and can
        # contain connection/auth material. Expose only the exception class.
        raise EmailDeliveryError(
            "smtp_" + type(exc).__name__.lower()
        ) from None

    if refused:
        raise EmailDeliveryError("recipient_refused")
    return str(config.get("provider") or "smtp")
