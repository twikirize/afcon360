"""
AFCON360 Unified Notification Service

Consolidated from app/services/notification_service.py and app/notifications/services.py.
Integrates channel handlers from app/notifications/channel_handlers/.
Connects to all domain models for contextual notification delivery.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, Any, Optional, List, Union, TYPE_CHECKING
from datetime import datetime, timezone
from flask import current_app, render_template
from flask_login import current_user
from sqlalchemy import func
from app.extensions import db, mail
from app.notifications.models import (
    Notification, NotificationType, NotificationChannel,
    NotificationTemplate, UserNotificationPreference, NotificationLog,
    NotificationStatus, Message, NotificationModule, MODULE_LABELS,
)
from app.notifications.channel_handlers import (
    EmailHandler, SmsHandler, PushHandler, InAppHandler, WebhookHandler,
)
from app.notifications.template_loader import template_loader
from app.notifications.utils import generate_idempotency_key, calculate_backoff
from app.notifications.preferences import PreferenceService

if TYPE_CHECKING:
    # Domain models used only for type annotations. These live in their own
    # modules and are NOT duplicated inside app/notifications/. Imported under
    # TYPE_CHECKING to document the exact SQLAlchemy classes each notification
    # helper accepts while avoiding circular imports at runtime
    # (`from __future__ import annotations` keeps annotations lazy).
    from app.identity.models.user import User
    from app.wallet.models.transaction import TransactionModel
    from app.accommodation.models.booking import AccommodationBooking
    from app.accommodation.models.property import Property
    from app.accommodation.models.review import Review
    from app.transport.models import Booking as TransportBooking, Vehicle
    from app.events.models import Event, EventRegistration
    from app.kyc.models import KycRecord

import enum

logger = logging.getLogger(__name__)


def _module_value(module) -> str:
    """Normalise a module argument (enum or string) to its string value."""
    if isinstance(module, NotificationModule):
        return module.value
    return str(module)


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

    # Channels that actually leave the platform (cost money / hit a provider).
    EXTERNAL_CHANNELS = {
        NotificationChannel.EMAIL,
        NotificationChannel.SMS,
        NotificationChannel.PUSH,
        NotificationChannel.WEBHOOK,
    }

    # ------------------------------------------------------------------
    # Module attribution
    # ------------------------------------------------------------------
    # AFCON360 runs several independent businesses (accommodation, transport,
    # events, wallet, tourism) on one notification system. Callers SHOULD pass
    # an explicit `module=` so a hotel booking is never confused with a bus
    # booking. This map is only a best-effort fallback for legacy/untagged
    # callers, keyed on notification type.
    #
    # NOTE: the shared booking types (booking_confirmed / booking_cancelled /
    # booking_update / payment_received) are deliberately ABSENT here — they are
    # genuinely ambiguous across modules and must be tagged explicitly by the
    # caller. Untagged, they fall through to SYSTEM rather than being silently
    # misfiled under the wrong business.
    TYPE_MODULE_FALLBACK = {
        # Accommodation-only types
        NotificationType.PROPERTY_SUBMITTED.value:          NotificationModule.ACCOMMODATION,
        NotificationType.PROPERTY_APPROVED.value:           NotificationModule.ACCOMMODATION,
        NotificationType.PROPERTY_REJECTED.value:           NotificationModule.ACCOMMODATION,
        NotificationType.PROPERTY_CHANGES_REQUESTED.value:  NotificationModule.ACCOMMODATION,
        NotificationType.PROPERTY_SUSPENDED.value:          NotificationModule.ACCOMMODATION,
        NotificationType.PROPERTY_REINSTATED.value:         NotificationModule.ACCOMMODATION,
        NotificationType.PROPERTY_ARCHIVED.value:           NotificationModule.ACCOMMODATION,
        NotificationType.PROPERTY_RESTORED.value:           NotificationModule.ACCOMMODATION,
        NotificationType.REVIEW_RECEIVED.value:             NotificationModule.ACCOMMODATION,
        # Transport-only types
        NotificationType.DRIVER_ASSIGNED.value:             NotificationModule.TRANSPORT,
        # Events-only types
        NotificationType.EVENT_REGISTERED.value:            NotificationModule.EVENTS,
        NotificationType.EVENT_REMINDER.value:              NotificationModule.EVENTS,
        # Wallet-only types
        NotificationType.DEPOSIT_CONFIRMED.value:           NotificationModule.WALLET,
        NotificationType.WITHDRAWAL_COMPLETED.value:        NotificationModule.WALLET,
        NotificationType.TRANSACTION_COMPLETED.value:       NotificationModule.WALLET,
        NotificationType.TRANSACTION_NOTIFICATION.value:    NotificationModule.WALLET,
        # Account / auth types
        NotificationType.VERIFICATION_EMAIL.value:          NotificationModule.ACCOUNT,
        NotificationType.PASSWORD_RESET.value:              NotificationModule.ACCOUNT,
        NotificationType.LOGIN_ALERT.value:                 NotificationModule.ACCOUNT,
        NotificationType.SIGNUP_NOTIFICATION.value:         NotificationModule.ACCOUNT,
        # Messaging
        NotificationType.INTERNAL_MESSAGE.value:            NotificationModule.MESSAGING,
        NotificationType.INTERNAL_REPLY.value:              NotificationModule.MESSAGING,
        NotificationType.MESSAGE_NOTIFICATION.value:        NotificationModule.MESSAGING,
        # System
        NotificationType.SYSTEM_ALERT.value:                NotificationModule.SYSTEM,
        NotificationType.PLATFORM_ANNOUNCEMENT.value:       NotificationModule.SYSTEM,
        NotificationType.ADMIN_NOTIFICATION.value:          NotificationModule.SYSTEM,
    }

    # Where each module's admin/operations dashboard lives, so an alert links
    # into the correct module console rather than a generic /admin page.
    MODULE_ADMIN_LINKS = {
        NotificationModule.ACCOMMODATION.value: '/accommodation/admin/bookings',
        NotificationModule.TRANSPORT.value:     '/transport/admin/dashboard',
        NotificationModule.EVENTS.value:        '/events/admin/dashboard',
        NotificationModule.WALLET.value:        '/admin/wallet-admin-dashboard',
        NotificationModule.TOURISM.value:       '/admin/tourism-admin-dashboard',
        NotificationModule.TOURNAMENT.value:    '/tournament',
        NotificationModule.KYC.value:           '/admin/compliance/kyc-queue',
        NotificationModule.IDENTITY.value:      '/admin/compliance/organisations',
        NotificationModule.COMPLIANCE.value:    '/admin/compliance/cases',
        NotificationModule.ACCOUNT.value:       '/admin/users',
        NotificationModule.MESSAGING.value:     '/api/notifications/messages',
        NotificationModule.SYSTEM.value:        '/admin',
    }

    @classmethod
    def _resolve_module(cls, module, notification_type) -> str:
        """
        Resolve the originating module for a notification.

        Explicit `module=` from the caller always wins. Otherwise fall back to
        the type map, and finally to SYSTEM. Never guesses between
        accommodation / transport / tourism for shared booking types.
        """
        if module:
            if isinstance(module, NotificationModule):
                return module.value
            try:
                return NotificationModule(str(module)).value
            except ValueError:
                logger.warning(
                    "Unknown notification module %r; falling back to 'system'", module
                )
                return NotificationModule.SYSTEM.value

        type_value = (
            notification_type.value
            if isinstance(notification_type, NotificationType)
            else str(notification_type)
        )
        return cls.TYPE_MODULE_FALLBACK.get(
            type_value, NotificationModule.SYSTEM
        ).value

    @staticmethod
    def module_for_booking(booking) -> str:
        """
        Infer the module for a booking-like object.

        Accommodation and transport bookings share notification types, so this
        inspects the concrete model to attribute the booking to the right
        business.
        """
        module_path = (getattr(type(booking), '__module__', '') or '').lower()
        if 'transport' in module_path:
            return NotificationModule.TRANSPORT.value
        if 'tourism' in module_path:
            return NotificationModule.TOURISM.value
        if 'accommodation' in module_path:
            return NotificationModule.ACCOMMODATION.value
        # Structural fallback: transport bookings carry driver/vehicle links.
        if hasattr(booking, 'driver_id') or hasattr(booking, 'vehicle_id'):
            return NotificationModule.TRANSPORT.value
        return NotificationModule.ACCOMMODATION.value

    @classmethod
    def _resolve_delivery_zone(
        cls,
        user_id: Optional[int],
        channels: list,
        notification_type: NotificationType,
        force_external: bool = False,
    ) -> List[str]:
        """
        Central "delivery zone" policy (architecture decision).

        Concept: the platform is the SOURCE OF TRUTH for in-system messaging, but
        users also live in the external world (Gmail, Yahoo, SMS, push). Some
        notifications must reach BOTH zones simultaneously — e.g. a hotel booking
        confirmation should appear in the user's in-app inbox AND arrive in their
        Gmail/Yahoo inbox.

        Rules applied here:
          * ``in_app`` is ALWAYS honoured for a known internal user (they always
            see it inside the system).
          * External channels (email/sms/push/webhook) fire when ANY of:
              1. the recipient is external (no ``user_id`` — e.g. a signup/OTP
                 email to an address that is not yet a user), OR
              2. the user has explicitly opted INTO that external channel for this
                 notification type (UserNotificationPreference), OR
              3. the caller passes ``force_external=True`` to demand dual delivery
                 (used by booking/wallet/transaction confirmations that must also
                 land in the user's real mailbox).

        This guarantees internal activity is always visible in-system, while
        outside-system communication reaches the real world only when intended.
        Webhook is treated as always-external (3rd-party subscribers).

        Returns the final list of channels to deliver on.
        """
        internal_channels = [c for c in channels if NotificationChannel(c) == NotificationChannel.IN_APP]
        external_channels = [c for c in channels if NotificationChannel(c) != NotificationChannel.IN_APP]

        # No external intent -> keep as-is (in_app only or already resolved).
        if not external_channels:
            return list(channels)

        # Webhook is always external (subscriber integration) — keep as-is.
        webhook_channels = [c for c in external_channels if NotificationChannel(c) == NotificationChannel.WEBHOOK]
        non_webhook_external = [c for c in external_channels if NotificationChannel(c) != NotificationChannel.WEBHOOK]

        # External recipient (no user) -> external channels are legitimate.
        if not user_id:
            return list(channels)

        # A caller that lists BOTH an external channel and in_app for a known user
        # is explicitly requesting dual delivery (in-app inbox + real mailbox),
        # e.g. booking/wallet/transaction confirmations. Honour that intent.
        dual_intent = bool(internal_channels) and bool(non_webhook_external)
        effective_force = force_external or dual_intent

        # Known internal user -> keep external channels they opted into or that
        # are explicitly forced (dual delivery).
        allowed_external = list(webhook_channels)
        for ch in non_webhook_external:
            if effective_force or PreferenceService.is_allowed(user_id, notification_type.value, [ch]):
                allowed_external.append(ch)

        # Always keep in_app so internal users still see it in their inbox.
        final = list(internal_channels) + allowed_external
        if not final:
            final = [NotificationChannel.IN_APP.value]
        return final

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
        force_external: bool = False,
        module: Union[str, 'NotificationModule'] = None,
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
            force_external: When True, an internal user's external channels
                (email/sms/push) are delivered in addition to in_app, enabling
                dual delivery (in-app inbox + real Gmail/Yahoo inbox). Used by
                booking/wallet/transaction confirmations.
            module: Originating business module (accommodation, transport,
                events, wallet, tourism, ...). SHOULD be passed explicitly —
                shared types like `booking_confirmed` are emitted by several
                modules and cannot be disambiguated from the type alone.

        Returns:
            Notification record or None on failure
        """
        try:
            if isinstance(notification_type, str):
                notification_type = NotificationType(notification_type)

            if not channels:
                channels = [NotificationChannel.IN_APP]

            # Apply the central delivery-zone policy: known internal users are
            # defaulted to in_app and external channels are added only when the
            # user opted in or the caller requests dual delivery (force_external).
            channels = cls._resolve_delivery_zone(user_id, channels, notification_type, force_external)

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
                module=cls._resolve_module(module, notification_type),
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
                handler = cls.HANDLERS.get(NotificationChannel(channel_str))

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
        module: Union[str, 'NotificationModule'] = None,
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
                module=module,
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
            module=NotificationModule.WALLET,
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

        # Build the scannable booking pass URL + QR code so the guest can
        # present it at check-in. Uses the configured public base URL so the QR
        # resolves on any device, not just the request host (which may be an
        # internal IP in production).
        pass_path = f"/accommodation/guest/pass/{booking.booking_reference}"
        pass_url = pass_path
        qr_uri = ''
        try:
            from app.utils.url import build_public_url
            pass_url = build_public_url(pass_path)
            qr_uri = cls._build_booking_qr(pass_url)
        except Exception:
            qr_uri = ''

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
                'pass_url': pass_url,
                'qr_data_uri': qr_uri,
            },
            channels=[channel],
            link=pass_url,
            priority='high' if notification_type == 'confirmed' else 'normal',
            module=NotificationModule.ACCOMMODATION,
        )

    @classmethod
    def _build_booking_qr(cls, pass_url: str) -> str:
        """Render a booking-pass QR code as a base64 data URI (best-effort)."""
        try:
            from app.utils.qr import qr_data_uri
            return qr_data_uri(pass_url, box_size=8, border=4)
        except Exception:
            return ''

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
            module=NotificationModule.TRANSPORT,
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
            module=NotificationModule.EVENTS,
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
            module=NotificationModule.ACCOMMODATION,
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
            module=NotificationModule.KYC,
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
    def get_unread_count(cls, user_id: int, module: str = None) -> int:
        """
        Count unread notifications for a user.

        Pass *module* to scope the badge to a single business, e.g. the
        transport dashboard showing only unread transport notifications.
        """
        query = Notification.query.filter_by(user_id=user_id, is_read=False)
        if module:
            query = query.filter_by(module=_module_value(module))
        return query.count()

    @classmethod
    def get_unread_counts_by_module(cls, user_id: int) -> Dict[str, int]:
        """
        Return `{module: unread_count}` for a user.

        Powers the per-module tabs/badges in the notification bell so a user can
        see at a glance that they have 2 transport items and 1 wallet item,
        rather than an undifferentiated "3".
        """
        try:
            rows = (
                db.session.query(Notification.module, func.count(Notification.id))
                .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
                .group_by(Notification.module)
                .all()
            )
            return {(m or 'system'): int(c) for m, c in rows}
        except Exception as e:
            logger.warning(f"get_unread_counts_by_module failed for user {user_id}: {e}")
            return {}

    @classmethod
    def get_user_notifications(
        cls,
        user_id: int,
        limit: int = 20,
        unread_only: bool = False,
        notification_type: str = None,
        module: Union[str, List[str]] = None,
    ) -> List[Notification]:
        """
        Get notifications for a user with optional filters.

        Args:
            module: Restrict to one module ('transport') or several
                (['transport', 'wallet']). Used by module dashboards so each
                business only surfaces its own activity.
        """
        query = Notification.query.filter_by(user_id=user_id)
        if unread_only:
            query = query.filter_by(is_read=False)
        if notification_type:
            query = query.filter_by(type=notification_type)
        if module:
            if isinstance(module, (list, tuple, set)):
                query = query.filter(
                    Notification.module.in_([_module_value(m) for m in module])
                )
            else:
                query = query.filter_by(module=_module_value(module))
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
                'title': notification.subject,
                'message': notification.body,
                'data': notification.context or {},
                'link': notification.link,
                'user_id': notification.user_id,
            }
            return render_template(template_name, **context)
        except Exception:
            return f"<h2>{notification.subject}</h2><p>{notification.body}</p>"

    @staticmethod
    def _send_email(notification: Notification):
        """Send email notification via the unified EmailHandler.

        Delegates to ``EmailHandler`` so all email delivery in the system
        flows through a single handler (see app/notifications/channel_handlers/email.py).
        """
        user = db.session.get(User, notification.user_id) if notification.user_id else None
        recipient = notification.email or (user.email if user else None)
        if not recipient:
            logger.warning(f"No email found for notification {notification.id}")
            return

        from app.notifications.channel_handlers.email import EmailHandler
        EmailHandler().deliver(
            notification,
            {'email': recipient, 'user_id': notification.user_id},
        )

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
        logger.info(f"Push to user_id={notification.user_id}: {notification.subject}")
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

        # Notify admins + support (account domain)
        cls._notify_admins(
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
            domain='account',
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
            cls._notify_admins(
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
                domain='wallet',
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
            domain='accommodation',
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
    def notify_kyc_reupload_requested(
        cls,
        user_id: int,
        document_label: str,
        reason: str,
        organisation_name: str = None,
    ):
        """Tell an account holder exactly which verification file to replace."""
        subject = f"{organisation_name} verification" if organisation_name else "identity verification"
        cls.send(
            user_id=user_id,
            notification_type=NotificationType.VERIFICATION_EMAIL,
            title="Verification document needs a clearer replacement",
            message=(
                f"Please replace the {document_label} for your {subject}. "
                f"Reason from compliance: {reason}"
            ),
            data={
                'document_label': document_label,
                'organisation_name': organisation_name,
            },
            channels=['email', 'in_app'],
            link="/kyc/status",
            priority='high',
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
            domain='kyc',
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
        """
        Booking confirmed → notify guest/customer + host/driver + module admins.

        Accommodation, transport and tourism bookings all flow through here but
        are DIFFERENT businesses with different customers. The originating
        module is resolved first and every notification is tagged with it, so a
        hotel booking never shows up in the transport inbox.
        """
        module = cls.module_for_booking(booking)
        ref = getattr(booking, 'booking_reference', getattr(booking, 'booking_code', 'N/A'))

        guest_id = getattr(booking, 'guest_user_id', None) or getattr(booking, 'customer_id', None)
        if guest_id:
            if module == NotificationModule.TRANSPORT.value:
                cls.send_transport_notification(guest_id, booking, 'confirmed', channel='email')
            else:
                cls.send_booking_notification(guest_id, booking, 'confirmed', channel='email')

        # Supply-side owner: property host (accommodation) or driver (transport).
        host_id = getattr(booking, 'host_user_id', None)
        if host_id:
            cls.send(
                user_id=host_id,
                notification_type=NotificationType.BOOKING_CONFIRMED,
                title="New Booking Received",
                message=f"You have a new booking (ref: {ref}).",
                data={'booking_id': getattr(booking, 'public_id', booking.id)},
                channels=['email', 'in_app', 'push'],
                link="/accommodation/host/bookings",
                priority='high',
                module=module,
            )

        cls._notify_admins(
            notification_type=NotificationType.BOOKING_CONFIRMED,
            title=f"{MODULE_LABELS.get(module, 'Booking')} Booking Confirmed",
            message=f"Booking {ref} was confirmed.",
            data={'booking_id': getattr(booking, 'public_id', booking.id)},
            link=cls.MODULE_ADMIN_LINKS.get(module, '/admin'),
            channels=['in_app'],
            domain=module,
            module=module,
        )

    @classmethod
    def notify_booking_cancelled(cls, booking, cancelled_by: int = None):
        """Booking cancelled → notify guest/customer + host + module admins."""
        module = cls.module_for_booking(booking)
        ref = getattr(booking, 'booking_reference', getattr(booking, 'booking_code', 'N/A'))

        guest_id = getattr(booking, 'guest_user_id', None) or getattr(booking, 'customer_id', None)
        if guest_id:
            if module == NotificationModule.TRANSPORT.value:
                cls.send_transport_notification(guest_id, booking, 'cancelled', channel='email')
            else:
                cls.send_booking_notification(guest_id, booking, 'cancelled', channel='email')

        host_id = getattr(booking, 'host_user_id', None)
        if host_id:
            cls.send(
                user_id=host_id,
                notification_type=NotificationType.BOOKING_CANCELLED,
                title="Booking Cancelled",
                message=f"A booking (ref: {ref}) was cancelled.",
                data={'booking_id': getattr(booking, 'public_id', booking.id), 'cancelled_by': cancelled_by},
                channels=['email', 'in_app'],
                priority='normal',
                module=module,
            )

        cls._notify_admins(
            notification_type=NotificationType.BOOKING_CANCELLED,
            title=f"{MODULE_LABELS.get(module, 'Booking')} Booking Cancelled",
            message=f"Booking {ref} was cancelled.",
            data={'booking_id': getattr(booking, 'public_id', booking.id), 'cancelled_by': cancelled_by},
            link=cls.MODULE_ADMIN_LINKS.get(module, '/admin'),
            channels=['in_app'],
            domain=module,
            module=module,
        )

    @classmethod
    def notify_check_in(cls, booking):
        module = cls.module_for_booking(booking)
        ref = getattr(booking, 'booking_reference', getattr(booking, 'booking_code', 'N/A'))

        guest_id = getattr(booking, 'guest_user_id', None) or getattr(booking, 'customer_id', None)
        if guest_id:
            cls.send(
                user_id=guest_id,
                notification_type=NotificationType.BOOKING_CONFIRMED,
                title="Check-in Confirmed",
                message=f"Welcome! You have checked in to {ref}.",
                data={'booking_id': getattr(booking, 'public_id', booking.id)},
                channels=['in_app', 'push'],
                link="/accommodation/bookings",
                priority='normal',
                module=module,
            )

        # Supply-side owner: property host.
        host_id = getattr(booking, 'host_user_id', None)
        if host_id:
            cls.send(
                user_id=host_id,
                notification_type=NotificationType.BOOKING_CONFIRMED,
                title="Guest Checked In",
                message=f"Guest has checked in to booking {ref}.",
                data={'booking_id': getattr(booking, 'public_id', booking.id)},
                channels=['email', 'in_app', 'push'],
                link="/accommodation/host/bookings",
                priority='normal',
                module=module,
            )

    @classmethod
    def notify_check_out(cls, booking):
        module = cls.module_for_booking(booking)
        ref = getattr(booking, 'booking_reference', getattr(booking, 'booking_code', 'N/A'))

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
                module=module,
            )

        # Supply-side owner: property host.
        host_id = getattr(booking, 'host_user_id', None)
        if host_id:
            cls.send(
                user_id=host_id,
                notification_type=NotificationType.BOOKING_CANCELLED,
                title="Guest Checked Out",
                message=f"Guest has checked out of booking {ref}.",
                data={'booking_id': getattr(booking, 'public_id', booking.id)},
                channels=['email', 'in_app'],
                link="/accommodation/host/bookings",
                priority='normal',
                module=module,
            )

    @classmethod
    def notify_event_registered(cls, registration):
        user_id = getattr(registration, 'user_id', None)
        if user_id:
            cls.send_event_notification(user_id, registration, 'registered', channel='email')
        # Event managers need visibility of new registrations on their dashboard.
        cls._notify_admins(
            notification_type=NotificationType.EVENT_REGISTERED,
            title="New Event Registration",
            message=f"A new registration was received for event #{getattr(registration, 'event_id', 'N/A')}.",
            data={
                'registration_id': getattr(registration, 'public_id', getattr(registration, 'id', None)),
                'event_id': getattr(registration, 'event_id', None),
            },
            link="/events/admin/dashboard",
            channels=['in_app'],
            domain='events',
            module=NotificationModule.EVENTS,
        )

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
        cls._notify_admins(
            notification_type=NotificationType.DRIVER_ASSIGNED,
            title="Driver Assigned",
            message=f"A driver was assigned to booking #{getattr(booking, 'public_id', booking.id)}.",
            data={'booking_id': getattr(booking, 'public_id', booking.id), 'driver_name': driver_name},
            link="/transport/admin/dashboard",
            channels=['in_app'],
            domain='transport',
        )

    # ------------------------------------------------------------------
    # Compliance case lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def _compliance_case_messages(cls, case, event, resolution=None, note=None):
        """Build (title, message) for a compliance case lifecycle event."""
        num = case.case_number
        if event == 'created':
            return (
                f"New Compliance Case {num}",
                f"A new {case.case_type.value} compliance case '{case.title}' was opened "
                f"(priority: {case.priority.value}).",
            )
        if event == 'assigned':
            return (
                f"Compliance Case Assigned: {num}",
                f"Case '{case.title}' has been assigned to a compliance officer.",
            )
        if event == 'escalated':
            return (
                f"Compliance Case Escalated: {num}",
                f"Case '{case.title}' was escalated"
                + (f": {case.escalation_reason}" if case.escalation_reason else ''),
            )
        if event == 'resolved':
            return (
                f"Compliance Case Resolved: {num}",
                f"Case '{case.title}' has been resolved with status '{case.status.value}'."
                + (f" Resolution: {resolution}" if resolution else ''),
            )
        if event == 'note':
            return (
                f"New Note on Compliance Case {num}",
                f"A note was added to case '{case.title}'." + (f" {note}" if note else ''),
            )
        # status change (approve / reject / close / reopen / request_info)
        return (
            f"Compliance Case Updated: {num}",
            f"Case '{case.title}' status changed to '{case.status.value}'."
            + (f" {resolution}" if resolution else ''),
        )

    @classmethod
    def notify_compliance_case_event(
        cls,
        case,
        event: str,
        actor_id: int = None,
        resolution: str = None,
        note: str = None,
        priority: str = 'high',
    ):
        """
        Central dispatcher for compliance case lifecycle notifications.

        Concerned parties notified for every event:
          * The compliance team (compliance_officer + auditor) and platform
            admins (owner/super_admin/admin) — always (module=compliance).
          * The case assignee (if any) — internal in-app + email.
          * The case creator — internal in-app confirmation.
          * The subject of the review (case.user, or the organisation's primary
            contact) — external in-app + email when an outcome is communicated
            (status change / escalation / resolution).
          * On escalation, owner/super_admin get a dedicated high-priority alert.

        `event` is one of: created | assigned | status | escalated | resolved | note.
        """
        module = NotificationModule.COMPLIANCE
        link = f"/admin/compliance/case/{case.id}"

        type_map = {
            'created':   NotificationType.COMPLIANCE_CASE_CREATED,
            'assigned':  NotificationType.COMPLIANCE_CASE_ASSIGNED,
            'status':    NotificationType.COMPLIANCE_CASE_UPDATED,
            'escalated': NotificationType.COMPLIANCE_CASE_ESCALATED,
            'resolved':  NotificationType.COMPLIANCE_CASE_RESOLVED,
            'note':      NotificationType.COMPLIANCE_CASE_UPDATED,
        }
        nt = type_map.get(event, NotificationType.COMPLIANCE_CASE_UPDATED)

        title, message = cls._compliance_case_messages(
            case, event, resolution=resolution, note=note
        )
        data = {
            'case_id': case.id,
            'case_number': case.case_number,
            'case_type': case.case_type.value if hasattr(case.case_type, 'value') else str(case.case_type),
            'priority': case.priority.value if hasattr(case.priority, 'value') else str(case.priority),
            'status': case.status.value if hasattr(case.status, 'value') else str(case.status),
            'event': event,
        }

        # 1) Compliance team + platform admins (dual delivery).
        try:
            cls._notify_admins(
                notification_type=nt,
                title=title,
                message=message,
                data=data,
                link=link,
                channels=['email', 'in_app', 'push'],
                domain='compliance',
                module=module,
            )
        except Exception as e:
            logger.error(f"compliance team notification failed: {e}")

        # 2) Assignee (internal) — notified of actionable events.
        if case.assigned_to and event in ('assigned', 'status', 'escalated', 'resolved'):
            try:
                cls.send(
                    user_id=case.assigned_to,
                    notification_type=nt,
                    title=title,
                    message=message,
                    data=data,
                    channels=['email', 'in_app'],
                    link=link,
                    priority=priority,
                    module=module,
                )
            except Exception as e:
                logger.error(f"compliance assignee notification failed: {e}")

        # 3) Creator (internal) — confirmation, but skip if creator is the actor.
        if case.created_by and case.created_by not in (actor_id, case.assigned_to):
            try:
                cls.send(
                    user_id=case.created_by,
                    notification_type=nt,
                    title=title,
                    message=message,
                    data=data,
                    channels=['in_app'],
                    link=link,
                    priority=priority,
                    module=module,
                )
            except Exception as e:
                logger.error(f"compliance creator notification failed: {e}")

        # 4) Subject of the review (external party) — outcome communication.
        if event in ('status', 'escalated', 'resolved'):
            subject_user = case.user_id
            subject_org_contact = (
                case.organisation.primary_contact_user_id if case.organisation else None
            )
            ext_user_id = subject_user or subject_org_contact
            if ext_user_id:
                try:
                    cls.send(
                        user_id=ext_user_id,
                        notification_type=nt,
                        title=title,
                        message=message,
                        data=data,
                        channels=['email', 'in_app'],
                        link=link,
                        priority='high',
                        module=module,
                        force_external=True,
                    )
                except Exception as e:
                    logger.error(f"compliance subject notification failed: {e}")

        # 5) Escalation bumps owner/super_admin directly (in addition to team).
        if event == 'escalated':
            try:
                cls.notify_roles(
                    roles=['owner', 'super_admin'],
                    notification_type=NotificationType.COMPLIANCE_CASE_ESCALATED,
                    title=f"Compliance Case Escalated: {case.case_number}",
                    message=f"Case '{case.title}' was escalated"
                    + (f": {case.escalation_reason}" if case.escalation_reason else ''),
                    data={'case_id': case.id, 'case_number': case.case_number},
                    link=link,
                    channels=['email', 'in_app', 'push'],
                    priority='high',
                    module=module,
                )
            except Exception as e:
                logger.error(f"compliance escalation owner alert failed: {e}")

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    # Roles that always receive platform-wide operational alerts.
    CORE_ADMIN_ROLES = ('owner', 'super_admin', 'admin')

    # Domain → additional roles whose dashboards must receive that domain's
    # activity. Keeps specialist admins (event_manager, wallet_admin, ...) in
    # the loop instead of only owner/super_admin/admin.
    DOMAIN_ROLE_MAP = {
        'accommodation': ('accommodation_admin', 'moderator'),
        'transport':     ('transport_admin',),
        'events':        ('event_manager',),
        'wallet':        ('wallet_admin', 'compliance_officer'),
        'tourism':       ('tourism_admin',),
        'kyc':           ('compliance_officer', 'auditor'),
        'identity':      ('compliance_officer', 'auditor'),
        'compliance':    ('compliance_officer', 'auditor'),
        'account':       ('support',),
        'moderation':    ('moderator',),
        'support':       ('support',),
    }

    @classmethod
    def _resolve_recipient_roles(cls, domain: str = None, extra_roles=None) -> list:
        """
        Build the role list for an operational alert.

        Always includes owner/super_admin/admin, then adds the domain
        specialists (and any explicit extras) so every relevant dashboard
        receives the activity.
        """
        roles = set(cls.CORE_ADMIN_ROLES)
        if domain:
            roles.update(cls.DOMAIN_ROLE_MAP.get(domain, ()))
        if extra_roles:
            roles.update(extra_roles)
        return sorted(roles)

    @classmethod
    def notify_roles(
        cls,
        roles,
        notification_type,
        title,
        message,
        data=None,
        link='/dashboard',
        channels=None,
        priority='high',
        module=None,
    ) -> int:
        """
        Send an operational notification to every active user holding any of
        *roles*. De-duplicates users who hold several matching roles.

        Returns the number of users notified.
        """
        channels = channels or ['email', 'in_app', 'push']
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import Role

        try:
            recipients = (
                db.session.query(User)
                .join(UserRole, User.roles)
                .join(Role, UserRole.role)
                .filter(Role.name.in_(list(roles)))
                .distinct()
                .all()
            )
        except Exception as e:
            logger.error(f"notify_roles lookup failed for {roles}: {e}")
            return 0

        seen = set()
        count = 0
        for user in recipients:
            if user.id in seen:
                continue
            seen.add(user.id)
            # Respect deactivated accounts when the flag is present.
            if getattr(user, 'is_active', True) is False:
                continue
            try:
                cls.send(
                    user_id=user.id,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    data=data or {},
                    channels=channels,
                    link=link,
                    priority=priority,
                    module=module,
                )
                count += 1
            except Exception as e:
                logger.error(f"notify_roles send failed for user {user.id}: {e}")
        return count

    @classmethod
    def _notify_admins(
        cls,
        notification_type,
        title,
        message,
        data=None,
        link='/admin',
        channels=None,
        domain: str = None,
        extra_roles=None,
        module=None,
    ):
        """
        Notify platform administrators of a system event.

        By default this reaches owner/super_admin/admin. Passing *domain*
        also reaches the specialist role(s) that own that domain's dashboard
        (e.g. domain='wallet' also notifies wallet_admin + compliance_officer).

        *module* tags the resulting notifications so each module dashboard can
        filter to only its own business activity. When omitted it defaults to
        *domain*, since the two use the same vocabulary.
        """
        roles = cls._resolve_recipient_roles(domain=domain, extra_roles=extra_roles)
        return cls.notify_roles(
            roles=roles,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data,
            link=link,
            channels=channels,
            priority='high',
            module=module or domain,
        )


# Backward-compatible alias for existing code (module level)
NotificationService.send_notification = NotificationService.send