import logging
from . import BaseChannelHandler

logger = logging.getLogger(__name__)


class EmailHandler(BaseChannelHandler):
    channel_name = "email"

    def validate_recipient(self, recipient: dict) -> bool:
        email = recipient.get("email")
        return bool(email and "@" in email)

    def deliver(self, notification, recipient: dict) -> dict:
        to_email = recipient.get("email") or getattr(notification, "email", None)
        if not to_email:
            return {
                "success": False,
                "response_code": 400,
                "response_body": "invalid_recipient",
                "error_code": "invalid_recipient",
            }

        subject = getattr(notification, "subject", None) or "Notification"
        body_text = getattr(notification, "body", None) or ""
        notification_id = getattr(notification, "id", None)

        # Render the branded HTML body without putting message/recipient data
        # into application logs when rendering fails.
        html = None
        try:
            from app.notifications.template_loader import template_loader

            context = dict(
                title=subject,
                message=body_text,
                notification=notification,
                data=getattr(notification, "context", None) or {},
                link=getattr(notification, "link", None),
                user_id=getattr(notification, "user_id", None),
            )
            try:
                notification_type = getattr(
                    getattr(notification, "type", "system_alert"),
                    "value",
                    getattr(notification, "type", "system_alert"),
                )
                html = template_loader.env.get_template(
                    f"email/{notification_type}.html"
                ).render(**context)
            except Exception:
                html = template_loader.env.get_template(
                    "email/default.html"
                ).render(**context)
        except Exception as exc:
            logger.debug(
                "Email template rendering unavailable (exception_type=%s)",
                type(exc).__name__,
            )

        try:
            from app.notifications.email_transport import send_smtp_email

            provider = send_smtp_email(
                recipient=to_email,
                subject=subject,
                body=body_text,
                html=html,
            )
            logger.info(
                "Email provider accepted notification (notification_id=%s, provider=%s)",
                notification_id or "test",
                provider,
            )
            return {
                "success": True,
                "external_id": f"mail_{notification_id}" if notification_id else "mail_test",
                "response_code": 200,
                "response_body": "email_provider_accepted",
                "provider": provider,
            }
        except Exception as exc:
            error_code = getattr(exc, "code", "email_delivery_failed")
            # Do not log the exception string, recipient, subject or message.
            logger.warning(
                "Email provider delivery failed (notification_id=%s, error_code=%s)",
                notification_id or "test",
                error_code,
            )
            return {
                "success": False,
                "response_code": 502,
                "response_body": "email_delivery_failed",
                "error_code": error_code,
            }
