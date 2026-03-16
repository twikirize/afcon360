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
            booking = Booking.query.get(booking_id)
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
                recipients = [booking.customer_id]
                message_template = "Your booking #{booking_code} has been confirmed. Pickup at {pickup_time}."

            elif notification_type == 'driver_assigned':
                if booking.driver_id:
                    recipients = [booking.customer_id, booking.driver_id]
                    message_template = "Driver {driver_name} has been assigned to your booking #{booking_code}."

            elif notification_type == 'driver_arriving':
                recipients = [booking.customer_id]
                message_template = "Your driver is arriving in approximately {eta_minutes} minutes."

            elif notification_type == 'booking_completed':
                recipients = [booking.customer_id]
                if booking.driver_id:
                    recipients.append(booking.driver_id)
                message_template = "Booking #{booking_code} has been completed. Fare: ${final_price}."

            elif notification_type == 'booking_cancelled':
                recipients = [booking.customer_id]
                if booking.driver_id:
                    recipients.append(booking.driver_id)
                message_template = "Booking #{booking_code} has been cancelled. Reason: {cancellation_reason}."

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
            driver = DriverProfile.query.get(driver_id)
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
    def _format_message(template: str, booking: Booking,
                        extra_data: Dict[str, Any]) -> str:
        """Format notification message"""
        # Prepare template data
        template_data = {
            'booking_code': booking.booking_code,
            'pickup_time': booking.pickup_time.strftime('%I:%M %p') if booking.pickup_time else '',
            'pickup_location': booking.pickup_location.get('address', '') if isinstance(booking.pickup_location,
                                                                                        dict) else str(
                booking.pickup_location),
            'final_price': float(booking.final_price) if booking.final_price else float(
                booking.estimated_price) if booking.estimated_price else 0.0,
            'cancellation_reason': booking.cancellation_reason or 'unknown'
        }

        # Add driver info if available
        if booking.driver_id:
            driver = DriverProfile.query.get(booking.driver_id)
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
        """Send notification to a recipient"""
        try:
            # This is a simplified implementation
            # In production, integrate with email, SMS, push notification services

            # For now, just log the notification
            notification_data = {
                'recipient_id': recipient_id,
                'message': message,
                'notification_type': notification_type,
                'booking_id': booking_id,
                'is_driver': is_driver,
                'sent_at': datetime.now(timezone.utc).isoformat(),
                'channels': ['in_app']  # Could be ['email', 'sms', 'push', 'in_app']
            }

            current_app.logger.info(
                f"Notification sent: {notification_type} to recipient {recipient_id}"
            )

            # In production, you would:
            # 1. Store notification in database
            # 2. Send email via SMTP service
            # 3. Send SMS via Twilio/other provider
            # 4. Send push notification via Firebase/APNS

            return {
                'success': True,
                'channels': ['logged'],
                'notification_id': f"notif_{datetime.now().strftime('%Y%m%d%H%M%S')}_{recipient_id}"
            }

        except Exception as e:
            current_app.logger.error(f"Error sending to recipient {recipient_id}: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
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
