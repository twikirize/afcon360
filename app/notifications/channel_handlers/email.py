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

        subject = notification.subject or notification.title or 'Notification'
        body_text = notification.body or ''

        # Try to render the rich HTML email template (templates/notifications/email/<type>.html).
        html = None
        try:
            from flask import render_template, current_app
            if current_app:
                template_name = f"notifications/email/{notification.type}.html"
                from flask_mail import Message
                html = render_template(
                    template_name,
                    title=subject,
                    message=body_text,
                    notification=notification,
                    data=notification.context or {},
                    link=notification.link,
                    user_id=notification.user_id,
                )
        except Exception as e:
            logger.debug(f"[EmailHandler] No HTML template for {notification.type} ({e}); using text body")

        try:
            from flask_mail import Message
            from app.extensions import mail

            if mail.state is None:
                raise RuntimeError("Mail extension not initialised")

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
