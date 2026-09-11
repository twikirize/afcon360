#app/transport/notification_services.py
"""
AFCON360 Transport Module - Notification Service
Handles notifications for transport events
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.transport.models import Booking, DriverProfile, BookingStatus
from app.utils.exceptions import ValidationError, NotFoundError
from app.utils.monitoring import monitor_endpoint, record_metric


class NotificationService:
    """Service for sending transport notifications"""

    @staticmethod
    @monitor_endpoint("send_booking_notification")
    def send_booking_notification(booking_id: int,
                                  notification_type: str,
                                  data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send notification for booking events

        Args:
            booking_id: ID of booking
            notification_type: Type of notification
            data: Additional notification data

        Returns:
            Notification result
        """
        try:
            booking = db.session.get(Booking, booking_id)
            if not booking:
                raise NotFoundError(
                    message="Booking not found",
                    resource_type="booking",
                    resource_id=booking_id
                )

            # Determine recipients and message based on notification type
            recipients = []
            message_template = ""
            notification_data = data or {}

            if notification_type == 'booking_created':
                recipients = [booking.user_id]
                message_template = "Your booking #{booking_reference} has been confirmed. Pickup at {pickup_time}."

            elif notification_type == 'driver_assigned':
                if booking.assigned_driver_id:
                    recipients = [booking.user_id, booking.assigned_driver_id]
                    message_template = "Driver {driver_name} has been assigned to your booking #{booking_reference}."

            elif notification_type == 'driver_arriving':
                recipients = [booking.user_id]
                message_template = "Your driver is arriving in approximately {eta_minutes} minutes."

            elif notification_type == 'booking_completed':
                recipients = [booking.user_id]
                if booking.assigned_driver_id:
                    recipients.append(booking.assigned_driver_id)
                message_template = "Booking #{booking_reference} has been completed. Fare: ${final_price}."

            elif notification_type == 'booking_cancelled':
                recipients = [booking.user_id]
                if booking.assigned_driver_id:
                    recipients.append(booking.assigned_driver_id)
                message_template = "Booking #{booking_reference} has been cancelled. Reason: {cancellation_reason}."

            # Format message
            message = NotificationService._format_message(
                template=message_template,
                booking=booking,
                extra_data=notification_data
            )

            # Send notifications
            results = []
            for recipient_id in recipients:
                result = NotificationService._send_to_recipient(
                    recipient_id=recipient_id,
                    message=message,
                    notification_type=notification_type,
                    booking_id=booking_id
                )
                results.append(result)

            # Record metrics
            record_metric(
                'notification_sent',
                tags={
                    'notification_type': notification_type,
                    'booking_status': booking.status.value,
                    'recipient_count': len(recipients)
                },
                value=1
            )

            return {
                'success': True,
                'message': 'Notifications sent successfully',
                'data': {
                    'booking_id': booking_id,
                    'notification_type': notification_type,
                    'recipients': recipients,
                    'results': results
                }
            }

        except (NotFoundError, ValidationError) as e:
            raise
        except Exception as e:
            current_app.logger.error(f"Error sending notification: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Error sending notification: {str(e)}",
                'data': {'booking_id': booking_id, 'notification_type': notification_type}
            }

    @staticmethod
    @monitor_endpoint("send_driver_notification")
    def send_driver_notification(driver_id: int,
                                 notification_type: str,
                                 data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send notification to driver"""
        try:
            driver = db.session.get(DriverProfile, driver_id)
            if not driver:
                raise NotFoundError(
                    message="Driver not found",
                    resource_type="driver",
                    resource_id=driver_id
                )

            # Determine message based on notification type
            message_template = ""
            notification_data = data or {}

            if notification_type == 'new_booking':
                message_template = "New booking available! Pickup at {pickup_location}."

            elif notification_type == 'booking_accepted':
                message_template = "You have accepted booking #{booking_code}."

            elif notification_type == 'booking_completed':
                message_template = "Booking #{booking_code} completed. You earned ${earnings}."

            elif notification_type == 'status_change':
                message_template = "Your driver status has been changed to {status}."

            elif notification_type == 'payment_received':
                message_template = "Payment of ${amount} received for booking #{booking_code}."

            # Format message
            message = message_template.format(**notification_data)

            # Send to driver
            result = NotificationService._send_to_recipient(
                recipient_id=driver_id,
                message=message,
                notification_type=notification_type,
                is_driver=True
            )

            return {
                'success': True,
                'message': 'Driver notification sent',
                'data': {
                    'driver_id': driver_id,
                    'notification_type': notification_type,
                    'result': result
                }
            }

        except NotFoundError:
            raise
        except Exception as e:
            current_app.logger.error(f"Error sending driver notification: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Error sending notification: {str(e)}",
                'data': {'driver_id': driver_id, 'notification_type': notification_type}
            }

    @staticmethod
    def send_email(to: str, subject: str, body: str, link: str = None) -> Dict[str, Any]:
        """
        Send a plain transactional email (no notification-inbox record).

        Used by wallet event notifications and webhook dead-letter alerts.
        Best-effort and fail-silent: a broken email transport must never roll
        back the business operation that triggered it. Renders the branded
        AFCON360 HTML template (falling back to plain text) via the same
        flask_mail path as the unified EmailHandler.
        """
        try:
            if not to or "@" not in to:
                return {
                    'success': False,
                    'response_code': 400,
                    'response_body': 'No recipient email address',
                }

            html = None
            try:
                from app.notifications.template_loader import template_loader
                html = template_loader.env.get_template(
                    "email/default.html"
                ).render(title=subject, message=body, link=link)
            except Exception as e:
                current_app.logger.debug(
                    f"Could not render branded HTML for email '{subject}' ({e}); using text body"
                )

            from flask_mail import Message
            from app.extensions import mail

            msg = Message(subject=subject, recipients=[to], body=body, html=html)
            mail.send(msg)

            current_app.logger.info(f"Email sent to {to}: {subject}")
            return {
                'success': True,
                'response_code': 200,
                'response_body': 'Email delivered via SMTP',
            }
        except Exception as e:
            current_app.logger.error(f"Failed to send email to {to}: {e}")
            return {
                'success': False,
                'response_code': 500,
                'response_body': str(e),
            }

    @staticmethod
    def _format_message(template: str, booking: Booking,
                        extra_data: Dict[str, Any]) -> str:
        """Format notification message"""
        # Prepare template data
        template_data = {
            'booking_reference': booking.booking_reference,
            'pickup_time': booking.pickup_time.strftime('%I:%M %p') if booking.pickup_time else '',
            'pickup_location': booking.pickup_location.get('address', '') if isinstance(booking.pickup_location,
                                                                                        dict) else str(
                booking.pickup_location),
            'final_price': float(booking.final_price) if booking.final_price else float(
                booking.base_price) if booking.base_price else 0.0,
            'cancellation_reason': booking.cancellation_reason or 'unknown'
        }

        # Add driver info if available
        if booking.assigned_driver_id:
            driver = db.session.get(DriverProfile, booking.assigned_driver_id)
            if driver and driver.user:
                template_data['driver_name'] = driver.user.name or 'Driver'

        # Add extra data
        template_data.update(extra_data)

        # Format message
        return template.format(**template_data)

    @staticmethod
    def _send_to_recipient(recipient_id: int, message: str,
                           notification_type: str,
                           booking_id: Optional[int] = None,
                           is_driver: bool = False) -> Dict[str, Any]:
        """Send a notification to a recipient via the DURABLE notification
        path (TH-3-D2): the canonical app.notifications service persists an
        inbox record (module=transport) instead of only logging.

        Fail-safe by design: if the durable path is unavailable the
        notification degrades to a log line and never raises, so a broken
        notification transport can never roll back the business operation
        that triggered it.
        """
        try:
            from app.notifications.services import NotificationService as DurableService
            from app.notifications.models import (
                NotificationType,
                NotificationModule,
            )

            type_map = {
                'driver_assigned': NotificationType.DRIVER_ASSIGNED,
                'booking_created': NotificationType.BOOKING_CONFIRMED,
                'booking_confirmed': NotificationType.BOOKING_CONFIRMED,
                'booking_cancelled': NotificationType.BOOKING_CANCELLED,
                'cancelled': NotificationType.BOOKING_CANCELLED,
            }
            notification_type_enum = type_map.get(
                notification_type, NotificationType.BOOKING_UPDATE
            )

            # Resolve the actual user id (a driver recipient references a
            # DriverProfile; everyone else is already a user id).
            user_id = recipient_id
            if is_driver:
                profile = db.session.get(DriverProfile, recipient_id)
                user_id = profile.user_id if profile else None
            if not user_id:
                return {
                    'success': False,
                    'error': 'no resolvable user for recipient',
                }

            record = DurableService.send(
                user_id=user_id,
                notification_type=notification_type_enum,
                title=f"Transport {notification_type.replace('_', ' ').title()}",
                message=message,
                data={
                    'booking_id': booking_id,
                    'recipient_id': recipient_id,
                    'is_driver': is_driver,
                    'transport_type': notification_type,
                },
                channels=['in_app'],
                module=NotificationModule.TRANSPORT,
            )

            if record is None:
                current_app.logger.warning(
                    "Durable notification suppressed for %s -> %s",
                    notification_type, user_id,
                )

            return {
                'success': True,
                'channels': ['in_app'],
                'notification_id': f"{getattr(record, 'id', '') or 'n/a'}",
            }
        except Exception as e:
            current_app.logger.error(
                f"Error delivering durable notification to {recipient_id}: {e}",
                exc_info=True,
            )
            return {
                'success': False,
                'channels': ['logged_fallback'],
                'error': str(e),
            }

    @staticmethod
    @monitor_endpoint("send_bulk_notifications")
    def send_bulk_notifications(recipient_ids: List[int],
                                message: str,
                                notification_type: str) -> Dict[str, Any]:
        """Send bulk notifications"""
        try:
            results = []

            for recipient_id in recipient_ids:
                result = NotificationService._send_to_recipient(
                    recipient_id=recipient_id,
                    message=message,
                    notification_type=notification_type
                )
                results.append({
                    'recipient_id': recipient_id,
                    'success': result['success']
                })

            success_count = sum(1 for r in results if r['success'])

            return {
                'success': True,
                'data': {
                    'total_recipients': len(recipient_ids),
                    'successful': success_count,
                    'failed': len(recipient_ids) - success_count,
                    'results': results
                }
            }

        except Exception as e:
            current_app.logger.error(f"Error sending bulk notifications: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Error sending bulk notifications: {str(e)}",
                'data': {'total_recipients': len(recipient_ids)}
            }

# ------------------------
# Singleton getter (module-level)
# ------------------------
from threading import Lock

_notification_service_instance = None
_notification_service_lock = Lock()

def get_notification_service():
    """Singleton getter for NotificationService"""
    global _notification_service_instance
    if _notification_service_instance is None:
        with _notification_service_lock:
            if _notification_service_instance is None:
                _notification_service_instance = NotificationService()
    return _notification_service_instance

