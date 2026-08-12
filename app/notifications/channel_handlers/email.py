import logging
from . import BaseChannelHandler

logger = logging.getLogger(__name__)


class EmailHandler(BaseChannelHandler):
    channel_name = 'email'

    def validate_recipient(self, recipient: dict) -> bool:
        email = recipient.get('email')
        return bool(email and '@' in email)

    def deliver(self, notification, recipient: dict) -> dict:
        to_email = recipient.get('email') or notification.email
        if not to_email:
            return {
                'success': False,
                'response_code': 400,
                'response_body': 'No recipient email address',
            }

        subject = notification.subject or 'Notification'
        body_text = notification.body or ''

        # Render the rich HTML email template
        # (templates/notifications/email/<type>.html) via the Jinja Environment
        # directly so it works with or without a Flask request context (e.g.
        # standalone scripts, Celery tasks). Falls back to the generic
        # default.html (which renders title/message/link) so every email is sent
        # as branded HTML instead of plain text.
        html = None
        try:
            from app.notifications.template_loader import template_loader

            ctx = dict(
                title=subject,
                message=body_text,
                notification=notification,
                data=notification.context or {},
                link=notification.link,
                user_id=notification.user_id,
            )
            try:
                html = template_loader.env.get_template(
                    f"email/{notification.type}.html"
                ).render(**ctx)
            except Exception:
                # Type-specific template missing -> use the generic default.
                html = template_loader.env.get_template(
                    "email/default.html"
                ).render(**ctx)
        except Exception as e:
            logger.debug(f"[EmailHandler] Could not render HTML for {notification.type} ({e}); using text body")

        try:
            from flask_mail import Message
            from app.extensions import mail

            msg = Message(
                subject=subject,
                recipients=[to_email],
                body=body_text,
                html=html,
            )
            mail.send(msg)

            logger.info(
                f"[EmailHandler] Email sent to {to_email}: {subject}"
            )
            return {
                'success': True,
                'external_id': f"mail_{notification.id}",
                'response_code': 200,
                'response_body': 'Email delivered via SMTP',
            }
        except Exception as e:
            logger.error(f"[EmailHandler] Failed to send email to {to_email}: {e}")
            return {
                'success': False,
                'response_code': 500,
                'response_body': str(e),
            }
