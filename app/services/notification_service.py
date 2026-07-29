"""
Centralized Notification Service for all modules.
Handles all notification delivery across the system.
"""

from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone
from flask import current_app, render_template
from app.extensions import db, mail
from app.models.notification import Notification, NotificationType, NotificationChannel
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Centralized notification service used by all modules.
    Supports in-app, email, SMS, and push notifications.
    """

    @staticmethod
    def send(
        user_id: int,
        notification_type: Union[str, NotificationType],
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        channels: List[str] = None,
        link: str = None,
        priority: str = 'normal'
    ) -> Optional[Notification]:
        """
        Send a notification to a user.
        """
        try:
            # Convert string to enum if needed
            if isinstance(notification_type, str):
                notification_type = NotificationType(notification_type)
            
            # Default channels
            if not channels:
                channels = ['in_app']
            
            # 1. Create notification record
            notification = Notification(
                user_id=user_id,
                type=notification_type,
                title=title,
                message=message,
                data=data or {},
                link=link,
                priority=priority,
                status='pending',
                channels=channels,
                is_read=False
            )
            db.session.add(notification)
            db.session.flush()
            
            # 2. Send via configured channels
            success = True
            if 'in_app' in channels:
                # In-app notifications are stored, no need to send
                notification.status = 'sent'
                notification.sent_at = datetime.now(timezone.utc)
            
            if 'email' in channels:
                try:
                    NotificationService._send_email(notification)
                except Exception as e:
                    logger.error(f"Email failed for notification {notification.id}: {e}")
                    notification.error_message = f"Email failed: {str(e)}"
                    success = False
            
            if 'sms' in channels:
                try:
                    NotificationService._send_sms(notification)
                except Exception as e:
                    logger.error(f"SMS failed for notification {notification.id}: {e}")
                    success = False
            
            if 'push' in channels:
                try:
                    NotificationService._send_push(notification)
                except Exception as e:
                    logger.error(f"Push failed for notification {notification.id}: {e}")
                    success = False
            
            if not success and 'in_app' in channels:
                notification.status = 'sent'
            
            db.session.commit()
            return notification
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to send notification: {e}", exc_info=True)
            return None

    @staticmethod
    def _send_email(notification: Notification):
        """
        Send email notification using Flask-Mail.
        """
        from flask_mail import Message
        from app.identity.models.user import User
        
        user = User.query.get(notification.user_id)
        if not user or not user.email:
            logger.warning(f"No email found for user {notification.user_id}")
            return
        
        msg = Message(
            subject=notification.title,
            recipients=[user.email],
            html=NotificationService._render_email_template(notification),
            sender=current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@example.com')
        )
        
        mail.send(msg)
        notification.mark_sent()

    @staticmethod
    def _render_email_template(notification: Notification) -> str:
        """
        Render email template for notification.
        """
        templates = {
            'property_approved': 'email/property_approved.html',
            'property_rejected': 'email/property_rejected.html',
            'property_changes_requested': 'email/property_changes_requested.html',
            'property_suspended': 'email/property_suspended.html',
            'property_reinstated': 'email/property_reinstated.html',
            'property_archived': 'email/property_archived.html',
            'property_restored': 'email/property_restored.html',
            'booking_confirmed': 'email/booking_confirmed.html',
            'default': 'email/default.html'
        }
        
        template_name = templates.get(notification.type.value, templates['default'])
        
        context = {
            'title': notification.title,
            'message': notification.message,
            'data': notification.data,
            'link': notification.link,
            'user_id': notification.user_id
        }
        
        try:
            return render_template(template_name, **context)
        except Exception:
            return f"<h2>{notification.title}</h2><p>{notification.message}</p>"

    @staticmethod
    def _send_sms(notification: Notification):
        """Placeholder for SMS provider integration."""
        logger.info(f"SMS would be sent: {notification.message[:50]}...")

    @staticmethod
    def _send_push(notification: Notification):
        """Placeholder for Push provider integration."""
        logger.info(f"Push would be sent: {notification.title}")

    @staticmethod
    def get_unread_count(user_id: int) -> int:
        return Notification.query.filter_by(user_id=user_id, is_read=False).count()

    @staticmethod
    def get_user_notifications(user_id: int, limit: int = 20, unread_only: bool = False) -> List[Notification]:
        query = Notification.query.filter_by(user_id=user_id)
        if unread_only:
            query = query.filter_by(is_read=False)
        return query.order_by(Notification.created_at.desc()).limit(limit).all()
