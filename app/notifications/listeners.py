"""
AFCON360 Notification Listeners

Subscribes to lifecycle signals (app/notifications/signals.py) and dispatches
notifications via NotificationService. Registered once at app startup in
app/__init__.py via register_notification_listeners().
"""

import logging

logger = logging.getLogger(__name__)

# Strong references to the signal receivers. Blinker stores receivers as weak
# references by default; because the handlers below are defined as nested
# functions inside register_notification_listeners(), they would otherwise be
# garbage-collected once that function returns (silently dropping every
# listener). Keeping them in this module-level list prevents that.
_HANDLERS = []


def register_notification_listeners():
    """Connect all notification signal handlers. Safe to call once at startup."""
    try:
        from app.notifications.signals import (
            user_signed_up,
            kyc_submitted,
            kyc_approved,
            kyc_rejected,
            wallet_created,
            wallet_transaction,
            property_submitted,
            property_approved,
            property_rejected,
            property_suspended,
            booking_confirmed,
            booking_cancelled,
        booking_checked_in,
        booking_checked_out,
        booking_dates_modified,
            event_registered,
            event_reminder,
            transport_booking_created,
            transport_driver_assigned,
            message_sent,
        )
        from app.notifications.services import NotificationService
    except ImportError:
        logger.debug("Notification signals unavailable; listeners not registered")
        return

    # ---------------------------------------------------------------
    # Account lifecycle
    # ---------------------------------------------------------------
    @user_signed_up.connect
    def _on_signup(sender, **kwargs):
        try:
            NotificationService.send_signup_notification(
                user_id=kwargs.get('user_id'),
                user_data=kwargs.get('user_data', {}),
            )
        except Exception as e:
            logger.error(f"signup notification failed: {e}")

    # ---------------------------------------------------------------
    # KYC
    # ---------------------------------------------------------------
    @kyc_submitted.connect
    def _on_kyc_submitted(sender, **kwargs):
        try:
            NotificationService.notify_kyc_submitted(
                user_id=kwargs.get('user_id'), kyc_record=kwargs.get('record')
            )
        except Exception as e:
            logger.error(f"kyc submitted notification failed: {e}")

    @kyc_approved.connect
    def _on_kyc_approved(sender, **kwargs):
        try:
            NotificationService.notify_kyc_approved(
                user_id=kwargs.get('user_id'), kyc_record=kwargs.get('record')
            )
        except Exception as e:
            logger.error(f"kyc approved notification failed: {e}")

    @kyc_rejected.connect
    def _on_kyc_rejected(sender, **kwargs):
        try:
            NotificationService.notify_kyc_rejected(
                user_id=kwargs.get('user_id'),
                reason=kwargs.get('reason'),
                kyc_record=kwargs.get('record'),
            )
        except Exception as e:
            logger.error(f"kyc rejected notification failed: {e}")

    # ---------------------------------------------------------------
    # Wallet
    # ---------------------------------------------------------------
    @wallet_created.connect
    def _on_wallet_created(sender, **kwargs):
        try:
            NotificationService.notify_wallet_created(user_id=kwargs.get('user_id'))
        except Exception as e:
            logger.error(f"wallet created notification failed: {e}")

    @wallet_transaction.connect
    def _on_wallet_tx(sender, **kwargs):
        try:
            transaction = kwargs.get('transaction')
            user_id = kwargs.get('user_id') or (transaction.user_id if transaction else None)
            if transaction and user_id:
                NotificationService.send_transaction_notification(
                    user_id=user_id, transaction=transaction,
                    channels=kwargs.get('channels'),
                )
        except Exception as e:
            logger.error(f"wallet transaction notification failed: {e}")

    # ---------------------------------------------------------------
    # Property / Accommodation
    # ---------------------------------------------------------------
    @property_submitted.connect
    def _on_property_submitted(sender, **kwargs):
        try:
            prop = kwargs.get('property')
            if prop:
                NotificationService.notify_property_submitted(prop)
        except Exception as e:
            logger.error(f"property submitted notification failed: {e}")

    @property_approved.connect
    def _on_property_approved(sender, **kwargs):
        try:
            prop = kwargs.get('property')
            if prop:
                NotificationService.notify_property_approved(prop)
        except Exception as e:
            logger.error(f"property approved notification failed: {e}")

    @property_rejected.connect
    def _on_property_rejected(sender, **kwargs):
        try:
            prop = kwargs.get('property')
            if prop:
                NotificationService.notify_property_rejected(prop, reason=kwargs.get('reason'))
        except Exception as e:
            logger.error(f"property rejected notification failed: {e}")

    @property_suspended.connect
    def _on_property_suspended(sender, **kwargs):
        try:
            prop = kwargs.get('property')
            if prop:
                NotificationService.notify_property_suspended(prop, reason=kwargs.get('reason'))
        except Exception as e:
            logger.error(f"property suspended notification failed: {e}")

    # ---------------------------------------------------------------
    # Bookings (accommodation)
    # ---------------------------------------------------------------
    @booking_confirmed.connect
    def _on_booking_confirmed(sender, **kwargs):
        try:
            booking = kwargs.get('booking')
            if booking:
                NotificationService.notify_booking_confirmed(booking)
        except Exception as e:
            logger.error(f"booking confirmed notification failed: {e}")

    @booking_cancelled.connect
    def _on_booking_cancelled(sender, **kwargs):
        try:
            booking = kwargs.get('booking')
            if booking:
                NotificationService.notify_booking_cancelled(
                    booking, cancelled_by=kwargs.get('cancelled_by')
                )
        except Exception as e:
            logger.error(f"booking cancelled notification failed: {e}")

    @booking_checked_in.connect
    def _on_booking_checked_in(sender, **kwargs):
        try:
            booking = kwargs.get('booking')
            if booking:
                NotificationService.notify_check_in(booking)
        except Exception as e:
            logger.error(f"booking checked-in notification failed: {e}")

    @booking_checked_out.connect
    def _on_booking_checked_out(sender, **kwargs):
        try:
            booking = kwargs.get('booking')
            if booking:
                NotificationService.notify_check_out(booking)
        except Exception as e:
            logger.error(f"booking checked-out notification failed: {e}")

    @booking_dates_modified.connect
    def _on_booking_dates_modified(sender, **kwargs):
        try:
            booking = kwargs.get('booking')
            adjustment = kwargs.get('adjustment')
            notify_guest = kwargs.get('notify_guest', False)
            if booking:
                NotificationService.notify_booking_dates_modified(
                    booking, adjustment, notify_guest=notify_guest
                )
        except Exception as e:
            logger.error(f"booking dates modified notification failed: {e}")

    # ---------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------
    @event_registered.connect
    def _on_event_registered(sender, **kwargs):
        try:
            reg = kwargs.get('registration')
            if reg:
                NotificationService.notify_event_registered(reg)
        except Exception as e:
            logger.error(f"event registered notification failed: {e}")

    # Also subscribe to the Events module's existing signal (different object)
    try:
        from app.events.signal_handlers import event_registered as events_event_registered
        @events_event_registered.connect
        def _on_events_event_registered(sender, **kwargs):
            try:
                from app.events.models import EventRegistration
                reg_id = kwargs.get('registration_id')
                if reg_id:
                    reg = EventRegistration.query.get(reg_id)
                    if reg:
                        NotificationService.notify_event_registered(reg)
            except Exception as e:
                logger.error(f"events event_registered notification failed: {e}")
    except ImportError:
        pass

    @event_reminder.connect
    def _on_event_reminder(sender, **kwargs):
        try:
            reg = kwargs.get('registration')
            if reg:
                NotificationService.notify_event_reminder(
                    reg, event_name=kwargs.get('event_name')
                )
        except Exception as e:
            logger.error(f"event reminder notification failed: {e}")

    # ---------------------------------------------------------------
    # Transport
    # ---------------------------------------------------------------
    @transport_booking_created.connect
    def _on_transport_booking(sender, **kwargs):
        try:
            booking = kwargs.get('booking')
            if booking:
                NotificationService.notify_booking_confirmed(booking)
        except Exception as e:
            logger.error(f"transport booking notification failed: {e}")

    @transport_driver_assigned.connect
    def _on_driver_assigned(sender, **kwargs):
        try:
            booking = kwargs.get('booking')
            if booking:
                NotificationService.notify_driver_assigned(
                    booking, driver_name=kwargs.get('driver_name')
                )
        except Exception as e:
            logger.error(f"driver assigned notification failed: {e}")

    # ---------------------------------------------------------------
    # Internal messaging
    # ---------------------------------------------------------------
    @message_sent.connect
    def _on_message_sent(sender, **kwargs):
        try:
            message = kwargs.get('message')
            if message:
                NotificationService.send_message_notification(
                    sender_id=kwargs.get('sender_id'),
                    recipient_id=kwargs.get('recipient_id'),
                    message=message,
                )
        except Exception as e:
            logger.error(f"message notification failed: {e}")

    _HANDLERS.extend([
        _on_signup, _on_kyc_submitted, _on_kyc_approved, _on_kyc_rejected,
        _on_wallet_created, _on_wallet_tx, _on_property_submitted, _on_property_approved,
        _on_property_rejected, _on_property_suspended, _on_booking_confirmed,
        _on_booking_cancelled, _on_booking_checked_in, _on_booking_checked_out,
        _on_booking_dates_modified,
        _on_event_registered, _on_events_event_registered, _on_event_reminder,
        _on_transport_booking, _on_driver_assigned, _on_message_sent,
    ])

    logger.info("✅ Notification listeners registered")
