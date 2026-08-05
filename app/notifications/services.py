"""
AFCON360 Unified Notification Service

Consolidated from app/services/notification_service.py and app/notifications/services.py.
Integrates channel handlers from app/notifications/channel_handlers/.
Connects to all domain models for contextual notification delivery.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone
from flask import current_app, render_template
from flask_login import current_user
from app.extensions import db, mail
from app.notifications.models import (
    Notification, NotificationType, NotificationChannel,
    NotificationTemplate, UserNotificationPreference, NotificationLog,
    NotificationStatus, Message,
)
from app.notifications.channel_handlers import (
    EmailHandler, SmsHandler, PushHandler, InAppHandler, WebhookHandler,
)
from app.notifications.template_loader import template_loader
from app.notifications.utils import generate_idempotency_key, calculate_backoff
from app.notifications.preferences import PreferenceService

import enum

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Centralized notification service used by all modules.
    Supports in-app, email, SMS, push, and webhook notifications.
    Integrates with all domain models for contextual delivery.
    """

    HANDLERS = {
        NotificationChannel.EMAIL: EmailHandler(),
        NotificationChannel.SMS: SmsHandler(),
        NotificationChannel.PUSH: PushHandler(),
        NotificationChannel.IN_APP: InAppHandler(),
        NotificationChannel.WEBHOOK: WebhookHandler(),
    }

    @classmethod
    def send(
        cls,
        user_id: int,
        notification_type: Union[str, NotificationType],
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        channels: List[str] = None,
        link: str = None,
        priority: str = 'normal',
        context: Dict[str, Any] = None,
        email: str = None,
        phone: str = None,
    ) -> Optional[Notification]:
        """
        Send a notification to a user across configured channels.

        Args:
            user_id: Target user's internal ID (BigInteger)
            notification_type: Enum or string type identifier
            title: Notification title
            message: Notification body message
            data: Additional context data (stored as JSON)
            channels: List of channels to deliver to (defaults to in_app)
            link: Deep link URL for in-app navigation
            priority: Priority level (high, normal, low)
            context: Rich context for template rendering
            email: Override email recipient (for non-user notifications)
            phone: Override phone recipient (for non-user notifications)

        Returns:
            Notification record or None on failure
        """
        try:
            if isinstance(notification_type, str):
                notification_type = NotificationType(notification_type)

            if not channels:
                channels = [NotificationChannel.IN_APP]

            # Resolve user info
            user = None
            if user_id:
                from app.identity.models.user import User
                user = db.session.get(User, user_id)

            recipient_email = email or (user.email if user else None)
            recipient_phone = phone or (user.phone if user else None)

            # Check user preferences
            if user_id and not PreferenceService.is_allowed(user_id, notification_type.value, channels):
                logger.info(
                    f"Notification {notification_type.value} suppressed for user {user_id} "
                    f"due to preference opt-out"
                )
                return None

            # Create notification record
            notification = Notification(
                user_id=user_id,
                email=recipient_email,
                phone=recipient_phone,
                type=notification_type,
                channel=NotificationChannel(channels[0]) if len(channels) == 1 else NotificationChannel.IN_APP,
                context=data or context or {},
                subject=title,
                body=message,
                priority=priority,
                status=NotificationStatus.PENDING,
                scheduled_for=None,
                attempts=0,
                external_id=str(uuid.uuid4()),
                link=link,
                is_read=False,
            )
            db.session.add(notification)
            db.session.flush()

            # Deliver via each channel
            results = []
            all_success = True

            for channel_str in channels:
                channel = NotificationChannel(channel_str)
                handler = cls.HANDLERS.get(channel_str)

                if not handler:
                    logger.warning(f"Unknown channel '{channel_str}' for notification {notification.id}")
                    all_success = False
                    continue

                # Validate recipient for channel
                recipient = {
                    'user_id': user_id,
                    'email': recipient_email,
                    'phone': recipient_phone,
                }
                if not handler.validate_recipient(recipient):
                    logger.warning(
                        f"Recipient validation failed for channel {channel_str} "
                        f"on notification {notification.id}"
                    )
                    all_success = False
                    continue

                # Deliver
                try:
                    result = handler.deliver(notification, recipient)
                    results.append({
                        'channel': channel_str,
                        'success': True,
                        'external_id': result.get('external_id'),
                        'response_code': result.get('response_code'),
                    })
                    cls._log_delivery(notification.id, channel_str, 'success', result)
                except Exception as e:
                    logger.error(
                        f"Delivery failed for notification {notification.id} "
                        f"via {channel_str}: {e}", exc_info=True
                    )
                    results.append({
                        'channel': channel_str,
                        'success': False,
                        'error': str(e),
                    })
                    cls._log_delivery(notification.id, channel_str, 'failure', {'error': str(e)})
                    all_success = False

            # Update notification status
            if all_success:
                notification.mark_delivered()
            elif NotificationChannel.IN_APP in channels:
                notification.mark_sent()
            else:
                notification.mark_failed("All channel deliveries failed")

            db.session.commit()
            return notification

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to send notification: {e}", exc_info=True)
            return None

    @classmethod
    def send_multi_channel(
        cls,
        user_id: int,
        notification_type: Union[str, NotificationType],
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        channels: List[str] = None,
        link: str = None,
        priority: str = 'normal',
        context: Dict[str, Any] = None,
    ) -> List[Optional[Notification]]:
        """
        Send a notification across multiple channels simultaneously.
        """
        channels = channels or [NotificationChannel.IN_APP]
        results = []
        for ch in channels:
            result = cls.send(
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                message=message,
                data=data,
                channels=[ch],
                link=link,
                priority=priority,
                context=context,
            )
            results.append(result)
        return results

    @classmethod
    def send_wallet_notification(
        cls,
        user_id: int,
        transaction: TransactionModel,
        channel: str = 'email',
    ) -> Optional[Notification]:
        """
        Send a wallet transaction notification with full context.
        """
        return cls.send(
            user_id=user_id,
            notification_type=NotificationType.TRANSACTION_COMPLETED,
            title=f"Transaction {'Credit' if transaction.tx_type.value == 'DEPOSIT' else 'Debit'}: {transaction.currency} {transaction.amount}",
            message=f"Your wallet has been {'credited' if transaction.tx_type.value == 'DEPOSIT' else 'debited'} "
                    f"with {transaction.currency} {transaction.amount}. "
                    f"New balance will be reflected shortly.",
            data={
                'transaction_id': transaction.public_id,
                'tx_type': transaction.tx_type.value,
                'amount': str(transaction.amount),
                'currency': transaction.currency,
                'balance': str(transaction.balance_after),
                'reference': transaction.client_request_id,
            },
            channels=[channel],
            link=f"/wallet/transactions/{transaction.public_id}",
            priority='high',
        )

    @classmethod
    def send_booking_notification(
        cls,
        user_id: int,
        booking: AccommodationBooking,
        notification_type: str,
        channel: str = 'email',
    ) -> Optional[Notification]:
        """
        Send an accommodation booking notification with full context.
        """
        type_map = {
            'confirmed': NotificationType.BOOKING_CONFIRMED,
            'cancelled': NotificationType.BOOKING_CANCELLED,
        }
        nt = type_map.get(notification_type, NotificationType.BOOKING_CONFIRMED)

        prop = getattr(booking, 'accommodation_property', None) or getattr(booking, 'listing', None)
        prop_title = getattr(prop, 'title', '') if prop else ''
        return cls.send(
            user_id=user_id,
            notification_type=nt,
            title=f"Booking {notification_type.capitalize()}: {booking.booking_reference}",
            message=f"Your booking for {prop_title or 'property'} "
                    f"has been {notification_type}.",
            data={
                'booking_id': booking.booking_reference,
                'booking_reference': booking.booking_reference,
                'property_title': prop_title,
                'check_in': booking.check_in.isoformat() if booking.check_in else '',
                'check_out': booking.check_out.isoformat() if booking.check_out else '',
                'total_amount': str(booking.total_amount) if booking.total_amount is not None else '',
                'currency': booking.currency or 'UGX',
            },
            channels=[channel],
            link=f"/accommodation/bookings/{booking.booking_reference}",
            priority='high' if notification_type == 'confirmed' else 'normal',
        )

    @classmethod
    def send_transport_notification(
        cls,
        user_id: int,
        booking: TransportBooking,
        notification_type: str,
        channel: str = 'email',
    ) -> Optional[Notification]:
        """
        Send a transport booking notification with full context.
        """
        type_map = {
            'confirmed': NotificationType.BOOKING_CONFIRMED,
            'driver_assigned': NotificationType.DRIVER_ASSIGNED,
            'cancelled': NotificationType.BOOKING_CANCELLED,
        }
        nt = type_map.get(notification_type, NotificationType.BOOKING_UPDATE)

        return cls.send(
            user_id=user_id,
            notification_type=nt,
            title=f"Transport {notification_type.replace('_', ' ').title()}",
            message=f"Your transport booking has been {notification_type}. "
                    f"Pickup: {booking.pickup_location or 'TBD'}",
            data={
                'booking_id': booking.id,
                'booking_code': booking.booking_code if hasattr(booking, 'booking_code') else '',
                'pickup_location': booking.pickup_location or '',
                'dropoff_location': booking.dropoff_location or '',
                'scheduled_time': booking.scheduled_time.isoformat() if hasattr(booking, 'scheduled_time') and booking.scheduled_time else '',
            },
            channels=[channel],
            link=f"/transport/bookings/{booking.id}",
            priority='normal',
        )

    @classmethod
    def send_event_notification(
        cls,
        user_id: int,
        registration: EventRegistration,
        notification_type: str,
        channel: str = 'email',
    ) -> Optional[Notification]:
        """
        Send an event registration notification with full context.
        """
        type_map = {
            'registered': NotificationType.EVENT_REGISTERED,
            'reminder': NotificationType.EVENT_REMINDER,
        }
        nt = type_map.get(notification_type, NotificationType.EVENT_REGISTERED)

        return cls.send(
            user_id=user_id,
            notification_type=nt,
            title=f"Event {notification_type.replace('_', ' ').title()}",
            message=f"You have successfully {notification_type.replace('_', ' ')} for the event.",
            data={
                'registration_id': registration.public_id if hasattr(registration, 'public_id') else '',
                'event_name': registration.event.name if hasattr(registration, 'event') and registration.event else '',
            },
            channels=[channel],
            link=f"/events/registrations/{registration.public_id if hasattr(registration, 'public_id') else ''}",
            priority='normal',
        )

    @classmethod
    def send_review_notification(
        cls,
        user_id: int,
        review: Review,
        channel: str = 'in_app',
    ) -> Optional[Notification]:
        """
        Send a review received notification.
        """
        return cls.send(
            user_id=user_id,
            notification_type=NotificationType.REVIEW_RECEIVED,
            title="New Review Received",
            message=f"You received a {review.rating}-star review for {review.property.title if review.property else 'your property'}.",
            data={
                'review_id': review.public_id if hasattr(review, 'public_id') else '',
                'rating': review.rating,
                'property_title': review.property.title if review.property else '',
            },
            channels=[channel],
            link=f"/accommodation/reviews/{review.public_id if hasattr(review, 'public_id') else ''}",
            priority='normal',
        )

    @classmethod
    def send_kyc_notification(
        cls,
        user_id: int,
        kyc_record: KycRecord,
        notification_type: str,
        channel: str = 'email',
    ) -> Optional[Notification]:
        """
        Send a KYC verification notification.
        """
        type_map = {
            'submitted': NotificationType.VERIFICATION_EMAIL,
            'approved': NotificationType.VERIFICATION_EMAIL,
            'rejected': NotificationType.VERIFICATION_EMAIL,
        }
        nt = type_map.get(notification_type, NotificationType.VERIFICATION_EMAIL)

        return cls.send(
            user_id=user_id,
            notification_type=nt,
            title=f"KYC {notification_type.replace('_', ' ').title()}",
            message=f"Your KYC verification has been {notification_type.replace('_', ' ')}. "
                    f"Please check your account for details.",
            data={
                'kyc_record_id': kyc_record.id,
                'status': kyc_record.status,
            },
            channels=[channel],
            link=f"/profile/kyc",
            priority='high' if notification_type == 'approved' else 'normal',
        )

    @classmethod
    def send_organisation_notification(
        cls,
        user_id: int,
        org: Organisation,
        notification_type: str,
        channel: str = 'email',
    ) -> Optional[Notification]:
        """
        Send an organisation-related notification.
        """
        return cls.send(
            user_id=user_id,
            notification_type=NotificationType.SYSTEM_ALERT,
            title=f"Organisation Update: {org.name}",
            message=f"Your organisation '{org.name}' has been updated.",
            data={
                'org_id': org.public_id if hasattr(org, 'public_id') else '',
                'org_name': org.name,
            },
            channels=[channel],
            link=f"/organisations/{org.public_id if hasattr(org, 'public_id') else ''}",
            priority='normal',
        )

    @classmethod
    def get_unread_count(cls, user_id: int) -> int:
        """Get count of unread notifications for a user."""
        return Notification.query.filter_by(user_id=user_id, is_read=False).count()

    @classmethod
    def get_user_notifications(
        cls,
        user_id: int,
        limit: int = 20,
        unread_only: bool = False,
        notification_type: str = None,
    ) -> List[Notification]:
        """Get notifications for a user with optional filters."""
        query = Notification.query.filter_by(user_id=user_id)
        if unread_only:
            query = query.filter_by(is_read=False)
        if notification_type:
            query = query.filter_by(type=notification_type)
        return query.order_by(Notification.created_at.desc()).limit(limit).all()

    @classmethod
    def mark_read(cls, notification_id: int, user_id: int) -> bool:
        """Mark a specific notification as read."""
        notification = Notification.query.filter_by(
            id=notification_id, user_id=user_id
        ).first()
        if notification:
            notification.mark_read()
            db.session.commit()
            return True
        return False

    @classmethod
    def mark_all_read(cls, user_id: int) -> int:
        """Mark all unread notifications as read."""
        unread = Notification.query.filter_by(user_id=user_id, is_read=False).all()
        count = len(unread)
        for notification in unread:
            notification.mark_read()
        if count > 0:
            db.session.commit()
        return count

    @classmethod
    def resend_failed(cls, max_retries: int = 3) -> int:
        """
        Resend failed notifications with exponential backoff.
        """
        failed = Notification.query.filter_by(status=NotificationStatus.FAILED).all()
        resent = 0
        for notification in failed:
            if notification.attempts and notification.attempts >= max_retries:
                logger.warning(
                    f"Notification {notification.id} exceeded max retries ({max_retries}), skipping"
                )
                continue

            delay = calculate_backoff(notification.attempts or 0)
            logger.info(
                f"Resending notification {notification.id} after {delay}s delay "
                f"(attempt {notification.attempts + 1})"
            )

            notification.increment_attempts()
            notification.status = NotificationStatus.PENDING
            notification.scheduled_for = datetime.now(timezone.utc)
            db.session.commit()

            # Re-deliver
            handler = cls.HANDLERS.get(notification.channel)
            if handler:
                try:
                    user = db.session.get(User, notification.user_id) if notification.user_id else None
                    recipient = {
                        'user_id': notification.user_id,
                        'email': notification.email or (user.email if user else None),
                        'phone': notification.phone or (user.phone if user else None),
                    }
                    result = handler.deliver(notification, recipient)
                    cls._log_delivery(notification.id, notification.channel, 'success', result)
                    notification.mark_delivered()
                    resent += 1
                except Exception as e:
                    logger.error(f"Resend failed for notification {notification.id}: {e}")
                    notification.mark_failed(str(e))
                    cls._log_delivery(notification.id, notification.channel, 'failure', {'error': str(e)})

        if resent > 0:
            db.session.commit()
        return resent

    @classmethod
    def _log_delivery(
        cls,
        notification_id: int,
        channel: str,
        status: str,
        response: dict,
    ) -> None:
        """Log a delivery attempt."""
        try:
            log = NotificationLog(
                notification_id=notification_id,
                channel=channel,
                status=status,
                response_code=response.get('response_code'),
                response_body=str(response.get('response_body', ''))[:500],
            )
            db.session.add(log)
        except Exception as e:
            logger.error(f"Failed to log notification delivery: {e}")

    @staticmethod
    def _render_email_template(notification: Notification) -> str:
        """Render email template for notification."""
        try:
            template_name = f"email/{notification.type}.html"
            context = {
                'title': notification.subject or notification.title,
                'message': notification.body,
                'data': notification.context or {},
                'link': notification.link,
                'user_id': notification.user_id,
            }
            return render_template(template_name, **context)
        except Exception:
            return f"<h2>{notification.title}</h2><p>{notification.body}</p>"

    @staticmethod
    def _send_email(notification: Notification):
        """Send email notification using Flask-Mail."""
        from flask_mail import Message

        user = db.session.get(User, notification.user_id) if notification.user_id else None
        recipient = notification.email or (user.email if user else None)
        if not recipient:
            logger.warning(f"No email found for notification {notification.id}")
            return

        msg = Message(
            subject=notification.subject or notification.title,
            recipients=[recipient],
            html=NotificationService._render_email_template(notification),
            sender=current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@afcon360.com'),
        )
        mail.send(msg)
        notification.mark_sent()

    @staticmethod
    def _send_sms(notification: Notification):
        """Send SMS notification."""
        user = db.session.get(User, notification.user_id) if notification.user_id else None
        recipient = notification.phone or (user.phone if user else None)
        if not recipient:
            logger.warning(f"No phone found for notification {notification.id}")
            return
        logger.info(f"SMS to {recipient}: {notification.body[:160]}...")
        notification.mark_sent()

    @staticmethod
    def _send_push(notification: Notification):
        """Send push notification via FCM."""
        user = db.session.get(User, notification.user_id) if notification.user_id else None
        if not user:
            logger.warning(f"No user found for push notification {notification.id}")
            return
        logger.info(f"Push to user_id={notification.user_id}: {notification.title}")
        notification.mark_sent()


# ============================================================================
# Internal Messaging Methods
# ============================================================================

    @classmethod
    def send_internal_message(
        cls,
        sender_id: int,
        recipient_id: int,
        subject: str,
        body: str,
        message_type: str = 'in_app',
        direction: str = 'outbound',
        priority: str = 'normal',
        parent_id: int = None,
    ) -> Message:
        """
        Send an internal message between users.

        Args:
            sender_id: ID of the sender
            recipient_id: ID of the recipient
            subject: Message subject
            body: Message body
            message_type: Delivery type (in_app, email, sms, push)
            direction: Message direction (inbound, outbound, system)
            priority: Message priority
            parent_id: Parent message ID for threading

        Returns:
            Message record
        """
        try:
            message = Message(
                sender_id=sender_id,
                recipient_id=recipient_id,
                subject=subject,
                body=body,
                message_type=message_type,
                direction=direction,
                priority=priority,
                parent_id=parent_id,
            )
            db.session.add(message)
            db.session.flush()

            # Create notification for recipient
            NotificationService.send(
                user_id=recipient_id,
                notification_type=NotificationType.INTERNAL_MESSAGE,
                title=subject or "New Message",
                message=body[:200],
                data={
                    'message_id': message.id,
                    'sender_id': sender_id,
                    'direction': direction,
                },
                channels=['in_app'],
                link=f"/messages/{message.id}",
                priority=priority,
            )

            db.session.commit()
            return message

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to send internal message: {e}", exc_info=True)
            return None

    @classmethod
    def send_system_message(
        cls,
        recipient_id: int,
        subject: str,
        body: str,
        channels: list = None,
        priority: str = 'high',
    ) -> Message:
        """
        Send a system-generated message to a user.
        """
        return cls.send_internal_message(
            sender_id=0,  # System sender
            recipient_id=recipient_id,
            subject=subject,
            body=body,
            message_type='in_app',
            direction='system',
            priority=priority,
        )

    @classmethod
    def send_admin_notification(
        cls,
        admin_id: int,
        recipient_id: int,
        subject: str,
        body: str,
        channels: list = None,
        priority: str = 'normal',
    ) -> Message:
        """
        Send an admin notification to a user.
        """
        return cls.send_internal_message(
            sender_id=admin_id,
            recipient_id=recipient_id,
            subject=subject,
            body=body,
            message_type='in_app',
            direction='outbound',
            priority=priority,
        )

    @classmethod
    def get_user_messages(
        cls,
        user_id: int,
        limit: int = 20,
        unread_only: bool = False,
        direction: str = None,
        archived: bool = False,
    ) -> list:
        """
        Get messages for a user with optional filters.
        """
        query = Message.query.filter(
            db.or_(
                Message.sender_id == user_id,
                Message.recipient_id == user_id,
            )
        )
        if unread_only:
            query = query.filter_by(is_read=False, recipient_id=user_id)
        if direction:
            query = query.filter_by(direction=direction)
        if not archived:
            query = query.filter_by(archived=False)
        return query.order_by(Message.created_at.desc()).limit(limit).all()

    @classmethod
    def mark_message_read(cls, message_id: int, user_id: int) -> bool:
        """Mark a message as read."""
        message = Message.query.filter_by(
            id=message_id, recipient_id=user_id
        ).first()
        if message:
            message.mark_read()
            db.session.commit()
            return True
        return False

    @classmethod
    def mark_all_messages_read(cls, user_id: int) -> int:
        """Mark all unread messages as read."""
        unread = Message.query.filter_by(
            recipient_id=user_id, is_read=False, archived=False
        ).all()
        count = len(unread)
        for message in unread:
            message.mark_read()
        if count > 0:
            db.session.commit()
        return count

    @classmethod
    def archive_message(cls, message_id: int, user_id: int) -> bool:
        """Archive a message."""
        message = Message.query.filter_by(
            id=message_id, recipient_id=user_id
        ).first()
        if message:
            message.archive()
            db.session.commit()
            return True
        return False

    @classmethod
    def send_signup_notification(cls, user_id: int, user_data: dict) -> None:
        """
        Send notifications when a new user signs up.
        Notifies the user and the admin.
        """
        # Notify the new user
        NotificationService.send(
            user_id=user_id,
            notification_type=NotificationType.SIGNUP_NOTIFICATION,
            title="Welcome to AFCON360",
            message="Your account has been created successfully. Welcome aboard!",
            data={'username': user_data.get('username', ''), 'email': user_data.get('email', '')},
            channels=['email', 'in_app'],
            link="/dashboard",
            priority='normal',
        )

        # Notify admins
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import Role
        admins = (
            db.session.query(User)
            .join(UserRole, User.roles)
            .join(Role, UserRole.role)
            .filter(Role.name.in_(['owner', 'super_admin', 'admin']))
            .all()
        )
        for admin in admins:
            NotificationService.send(
                user_id=admin.id,
                notification_type=NotificationType.SIGNUP_NOTIFICATION,
                title="New User Signup",
                message=f"New user '{user_data.get('username', 'Unknown')}' signed up with email '{user_data.get('email', 'Unknown')}'.",
                data={
                    'new_user_id': user_id,
                    'username': user_data.get('username', ''),
                    'email': user_data.get('email', ''),
                    'role': user_data.get('role', 'user'),
                },
                channels=['email', 'in_app', 'push'],
                link="/admin/users",
                priority='high',
            )

    @classmethod
    def send_transaction_notification(
        cls,
        user_id: int,
        transaction: TransactionModel,
        channels: list = None,
    ) -> None:
        """
        Send transaction notifications to user and admins.
        """
        channels = channels or ['email', 'in_app']

        # Notify the user
        NotificationService.send_wallet_notification(
            user_id=user_id,
            transaction=transaction,
            channel=channels[0] if channels else 'email',
        )

        # Notify admins for large transactions (>= 1,000,000 UGX)
        if transaction.amount >= 1000000:
            from app.identity.models.user import User, UserRole
            from app.identity.models.roles_permission import Role
            admins = (
                db.session.query(User)
                .join(UserRole, User.roles)
                .join(Role, UserRole.role)
                .filter(Role.name.in_(['owner', 'super_admin', 'admin']))
                .all()
            )
            for admin in admins:
                NotificationService.send(
                    user_id=admin.id,
                    notification_type=NotificationType.TRANSACTION_COMPLETED,
                    title=f"Large Transaction Alert: {transaction.currency} {transaction.amount}",
                    message=f"Transaction {transaction.client_request_id} by user {user_id} "
                            f"amounts to {transaction.currency} {transaction.amount}. "
                            f"Status: {transaction.status.value}",
                    data={
                        'transaction_id': transaction.public_id,
                        'user_id': user_id,
                        'amount': str(transaction.amount),
                        'currency': transaction.currency,
                        'status': transaction.status.value,
                    },
                    channels=['email', 'in_app', 'push'],
                    link=f"/wallet/transactions/{transaction.public_id}",
                    priority='high',
                )

    @classmethod
    def send_message_notification(
        cls,
        sender_id: int,
        recipient_id: int,
        message: Message,
        channels: list = None,
    ) -> None:
        """
        Send a message notification to the recipient.
        """
        channels = channels or ['in_app']

        NotificationService.send(
            user_id=recipient_id,
            notification_type=NotificationType.MESSAGE_NOTIFICATION,
            title=f"New message from user {sender_id}",
            message=message.body[:200],
            data={
                'message_id': message.id,
                'sender_id': sender_id,
                'subject': message.subject,
            },
            channels=channels,
            link=f"/messages/{message.id}",
            priority='normal',
        )


    # ============================================================================
    # BROADCAST & ANNOUNCEMENTS
    # ============================================================================

    @classmethod
    def broadcast_announcement(
        cls,
        title: str,
        message: str,
        roles: list = None,
        channels: list = None,
        sender_id: int = None,
    ) -> int:
        """
        Send a platform announcement to all users, or to users with specific roles.

        Args:
            title: Announcement title
            message: Announcement body
            roles: List of role names to target (empty = all users)
            channels: List of channels (defaults to ['in_app', 'email'])
            sender_id: Admin/owner user id sending the broadcast

        Returns:
            Number of recipients the announcement was dispatched to.
        """
        from app.identity.models.user import User
        from app.identity.models.roles_permission import Role, UserRole

        channels = channels or ['in_app', 'email']

        if roles:
            recipients = (
                db.session.query(User)
                .join(UserRole, User.roles)
                .join(Role, UserRole.role)
                .filter(Role.name.in_(roles), User.is_active == True)
                .distinct()
                .all()
            )
        else:
            recipients = User.query.filter_by(is_active=True).all()

        count = 0
        for user in recipients:
            try:
                cls.send(
                    user_id=user.id,
                    notification_type=NotificationType.PLATFORM_ANNOUNCEMENT,
                    title=title,
                    message=message,
                    data={'broadcast': True, 'sender_id': sender_id},
                    channels=channels,
                    link='/dashboard',
                    priority='high',
                )
                count += 1
            except Exception as e:
                logger.error(f"Broadcast failed for user {user.id}: {e}")

        logger.info(f"Broadcast announcement '{title}' sent to {count} recipients")
        return count

    # ============================================================================
    # MODULE LIFECYCLE NOTIFICATION HOOKS
    # ============================================================================

    @classmethod
    def notify_property_submitted(cls, property_obj, submitted_by_id: int = None):
        """Host submitted a property for review → notify host + admins."""
        host_id = property_obj.owner_user_id
        cls.send(
            user_id=host_id,
            notification_type=NotificationType.PROPERTY_SUBMITTED,
            title="Property Submitted for Review",
            message=f"Your property '{property_obj.title}' has been submitted and is under review.",
            data={'property_id': property_obj.public_id, 'title': property_obj.title},
            channels=['email', 'in_app'],
            link=f"/accommodation/host/listings",
            priority='normal',
        )
        cls._notify_admins(
            notification_type=NotificationType.PROPERTY_SUBMITTED,
            title="New Property Pending Review",
            message=f"Property '{property_obj.title}' submitted by host #{host_id} awaits moderation.",
            data={'property_id': property_obj.public_id},
            link="/accommodation/admin/properties",
        )

    @classmethod
    def notify_property_approved(cls, property_obj):
        """Property approved → notify host only."""
        cls.send(
            user_id=property_obj.owner_user_id,
            notification_type=NotificationType.PROPERTY_APPROVED,
            title="Property Approved",
            message=f"Congratulations! Your property '{property_obj.title}' is now approved and live.",
            data={'property_id': property_obj.public_id},
            channels=['email', 'in_app', 'push'],
            link=f"/accommodation/detail/{property_obj.public_id}",
            priority='high',
        )

    @classmethod
    def notify_property_rejected(cls, property_obj, reason: str = None):
        cls.send(
            user_id=property_obj.owner_user_id,
            notification_type=NotificationType.PROPERTY_REJECTED,
            title="Property Rejected",
            message=f"Your property '{property_obj.title}' was rejected." + (f" Reason: {reason}" if reason else ""),
            data={'property_id': property_obj.public_id},
            channels=['email', 'in_app'],
            link=f"/accommodation/host/listings",
            priority='high',
        )

    @classmethod
    def notify_property_suspended(cls, property_obj, reason: str = None):
        cls.send(
            user_id=property_obj.owner_user_id,
            notification_type=NotificationType.PROPERTY_SUSPENDED,
            title="Property Suspended",
            message=f"Your property '{property_obj.title}' has been suspended." + (f" Reason: {reason}" if reason else ""),
            data={'property_id': property_obj.public_id},
            channels=['email', 'in_app'],
            priority='high',
        )

    @classmethod
    def notify_kyc_submitted(cls, user_id: int, kyc_record=None):
        cls.send(
            user_id=user_id,
            notification_type=NotificationType.VERIFICATION_EMAIL,
            title="KYC Verification Submitted",
            message="Your identity verification has been submitted and is under review.",
            data={'kyc_id': kyc_record.id if kyc_record else None},
            channels=['email', 'in_app'],
            link="/profile/kyc",
            priority='normal',
        )

    @classmethod
    def notify_kyc_approved(cls, user_id: int, kyc_record=None):
        cls.send(
            user_id=user_id,
            notification_type=NotificationType.VERIFICATION_EMAIL,
            title="KYC Verification Approved",
            message="Your identity verification has been approved. You now have full platform access.",
            data={'kyc_id': kyc_record.id if kyc_record else None, 'tier': getattr(kyc_record, 'tier', None)},
            channels=['email', 'in_app', 'push'],
            link="/profile/kyc",
            priority='high',
        )
        cls._notify_admins(
            notification_type=NotificationType.KYC_APPROVED if hasattr(NotificationType, 'KYC_APPROVED') else NotificationType.VERIFICATION_EMAIL,
            title="KYC Approved",
            message=f"User #{user_id} passed KYC verification.",
            data={'user_id': user_id},
            link="/admin/users",
        )

    @classmethod
    def notify_kyc_rejected(cls, user_id: int, reason: str = None, kyc_record=None):
        cls.send(
            user_id=user_id,
            notification_type=NotificationType.VERIFICATION_EMAIL,
            title="KYC Verification Rejected",
            message="Your identity verification was rejected." + (f" Reason: {reason}" if reason else ""),
            data={'kyc_id': kyc_record.id if kyc_record else None},
            channels=['email', 'in_app'],
            link="/profile/kyc",
            priority='high',
        )

    @classmethod
    def notify_wallet_created(cls, user_id: int):
        cls.send(
            user_id=user_id,
            notification_type=NotificationType.SYSTEM_ALERT,
            title="Wallet Created",
            message="Your AFCON360 wallet has been created. You can now send, receive, and store funds securely.",
            data={},
            channels=['in_app', 'email'],
            link="/wallet",
            priority='normal',
        )

    @classmethod
    def notify_payment_received(cls, user_id: int, transaction, payer_name: str = None):
        cls.send_wallet_notification(user_id=user_id, transaction=transaction, channel='email')
        if payer_name:
            cls.send(
                user_id=user_id,
                notification_type=NotificationType.PAYMENT_RECEIVED,
                title="Payment Received",
                message=f"You received a payment of {transaction.currency} {transaction.amount} from {payer_name}.",
                data={'transaction_id': transaction.public_id},
                channels=['email', 'in_app', 'push'],
                link=f"/wallet/transactions/{transaction.public_id}",
                priority='high',
            )

    @classmethod
    def notify_booking_confirmed(cls, booking):
        """Accommodation/transport booking confirmed → notify guest + host/driver."""
        guest_id = getattr(booking, 'guest_user_id', None) or getattr(booking, 'customer_id', None)
        if guest_id:
            cls.send_booking_notification(guest_id, booking, 'confirmed', channel='email')
        host_id = getattr(booking, 'host_user_id', None)
        if host_id:
            cls.send(
                user_id=host_id,
                notification_type=NotificationType.BOOKING_CONFIRMED,
                title="New Booking Received",
                message=f"You have a new booking (ref: {getattr(booking, 'booking_reference', getattr(booking, 'booking_code', 'N/A'))}).",
                data={'booking_id': getattr(booking, 'public_id', booking.id)},
                channels=['email', 'in_app', 'push'],
                link="/accommodation/host/bookings",
                priority='high',
            )

    @classmethod
    def notify_booking_cancelled(cls, booking, cancelled_by: int = None):
        guest_id = getattr(booking, 'guest_user_id', None) or getattr(booking, 'customer_id', None)
        if guest_id:
            cls.send_booking_notification(guest_id, booking, 'cancelled', channel='email')
        host_id = getattr(booking, 'host_user_id', None)
        if host_id:
            cls.send(
                user_id=host_id,
                notification_type=NotificationType.BOOKING_CANCELLED,
                title="Booking Cancelled",
                message=f"A booking (ref: {getattr(booking, 'booking_reference', getattr(booking, 'booking_code', 'N/A'))}) was cancelled.",
                data={'booking_id': getattr(booking, 'public_id', booking.id), 'cancelled_by': cancelled_by},
                channels=['email', 'in_app'],
                priority='normal',
            )

    @classmethod
    def notify_check_in(cls, booking):
        guest_id = getattr(booking, 'guest_user_id', None) or getattr(booking, 'customer_id', None)
        if guest_id:
            cls.send(
                user_id=guest_id,
                notification_type=NotificationType.BOOKING_CONFIRMED,
                title="Check-in Confirmed",
                message=f"Welcome! You have checked in to {getattr(booking, 'booking_reference', 'your booking')}.",
                data={'booking_id': getattr(booking, 'public_id', booking.id)},
                channels=['in_app', 'push'],
                link="/accommodation/bookings",
                priority='normal',
            )

    @classmethod
    def notify_check_out(cls, booking):
        guest_id = getattr(booking, 'guest_user_id', None) or getattr(booking, 'customer_id', None)
        if guest_id:
            cls.send(
                user_id=guest_id,
                notification_type=NotificationType.BOOKING_CANCELLED,
                title="Check-out Complete",
                message=f"Thank you for staying with us! Your check-out is complete.",
                data={'booking_id': getattr(booking, 'public_id', booking.id)},
                channels=['in_app', 'email'],
                link="/accommodation/bookings",
                priority='normal',
            )

    @classmethod
    def notify_event_registered(cls, registration):
        user_id = getattr(registration, 'user_id', None)
        if user_id:
            cls.send_event_notification(user_id, registration, 'registered', channel='email')

    @classmethod
    def notify_event_reminder(cls, registration, event_name: str = None):
        user_id = getattr(registration, 'user_id', None)
        if user_id:
            cls.send_event_notification(user_id, registration, 'reminder', channel='push')

    @classmethod
    def notify_driver_assigned(cls, booking, driver_name: str = None):
        guest_id = getattr(booking, 'customer_id', None)
        if guest_id:
            cls.send_transport_notification(guest_id, booking, 'driver_assigned', channel='sms')
        driver_id = getattr(booking, 'driver_id', None)
        if driver_id:
            cls.send(
                user_id=driver_id,
                notification_type=NotificationType.DRIVER_ASSIGNED,
                title="New Trip Assigned",
                message=f"You have been assigned a new trip.",
                data={'booking_id': booking.id},
                channels=['in_app', 'push'],
                link="/transport/driver/dashboard",
                priority='high',
            )

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    @classmethod
    def _notify_admins(cls, notification_type, title, message, data=None, link='/admin', channels=None):
        """Notify all owner/super_admin/admin users of a system event."""
        channels = channels or ['email', 'in_app', 'push']
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import Role
        admins = (
            db.session.query(User)
            .join(UserRole, User.roles)
            .join(Role, UserRole.role)
            .filter(Role.name.in_(['owner', 'super_admin', 'admin']))
            .all()
        )
        for admin in admins:
            cls.send(
                user_id=admin.id,
                notification_type=notification_type,
                title=title,
                message=message,
                data=data or {},
                channels=channels,
                link=link,
                priority='high',
            )


# Backward-compatible alias for existing code (module level)
NotificationService.send_notification = NotificationService.send