"""
Canonical event taxonomy + registry.

Architectural rule enforced here
--------------------------------
**Domain events are NOT notification types.** They are different concepts and
must not be conflated:

* ``payment.successful`` is a *fact* — it happened, it is immutable, and it may
  have many consequences (wallet credit, accounting entry, fraud check, audit
  record, analytics, AND possibly a notification).
* ``PAYMENT_RECEIVED`` is a *communication artefact* — one possible consequence.

Keeping them separate means adding a consumer never requires touching the
notification enum, and suppressing a notification never erases the fact.

Naming convention: ``<aggregate>.<past_tense_verb>``, lowercase, dot-separated.
Good: ``booking.confirmed``, ``kyc.approved``, ``payment.failed``.
Bad:  ``ConfirmBooking`` (that is a command), ``booking_confirm`` (not past tense).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from .exceptions import EventValidationError, UnknownEventTypeError

logger = logging.getLogger(__name__)


class EventType:
    """
    Canonical AFCON360 domain event types.

    Plain string constants (not an Enum) because event types must remain
    forward-compatible: a consumer running old code may legitimately receive an
    event type it does not know about, and an Enum lookup would raise instead of
    letting it skip gracefully.
    """

    # --- identity / account -------------------------------------------
    USER_REGISTERED = 'user.registered'
    USER_EMAIL_VERIFIED = 'user.email_verified'
    USER_PROFILE_UPDATED = 'user.profile_updated'
    USER_DEACTIVATED = 'user.deactivated'
    USER_REACTIVATED = 'user.reactivated'

    # --- security (feed audit + selectively notify) --------------------
    LOGIN_SUCCEEDED = 'security.login_succeeded'
    LOGIN_FAILED = 'security.login_failed'
    PASSWORD_CHANGED = 'security.password_changed'
    PASSWORD_RESET_REQUESTED = 'security.password_reset_requested'
    MFA_ENABLED = 'security.mfa_enabled'
    MFA_DISABLED = 'security.mfa_disabled'
    MFA_FAILED = 'security.mfa_failed'
    SESSION_REVOKED = 'security.session_revoked'
    DEVICE_REGISTERED = 'security.device_registered'
    API_KEY_CREATED = 'security.api_key_created'
    API_KEY_REVOKED = 'security.api_key_revoked'
    ADMIN_LOGIN = 'security.admin_login'
    ADMIN_ACTION = 'security.admin_action'
    PERMISSION_CHANGED = 'security.permission_changed'
    ROLE_CHANGED = 'security.role_changed'
    SUSPICIOUS_ACTIVITY = 'security.suspicious_activity'

    # --- KYC / compliance ---------------------------------------------
    KYC_SUBMITTED = 'kyc.submitted'
    KYC_REVIEW_STARTED = 'kyc.review_started'
    KYC_APPROVED = 'kyc.approved'
    KYC_REJECTED = 'kyc.rejected'
    KYC_EXPIRED = 'kyc.expired'

    # --- wallet / payments --------------------------------------------
    WALLET_CREATED = 'wallet.created'
    PAYMENT_INITIATED = 'payment.initiated'
    PAYMENT_PENDING = 'payment.pending'
    PAYMENT_SUCCESSFUL = 'payment.successful'
    PAYMENT_FAILED = 'payment.failed'
    PAYMENT_REFUNDED = 'payment.refunded'
    DEPOSIT_CONFIRMED = 'wallet.deposit_confirmed'
    WITHDRAWAL_COMPLETED = 'wallet.withdrawal_completed'
    TRANSACTION_COMPLETED = 'wallet.transaction_completed'
    LARGE_TRANSACTION_DETECTED = 'wallet.large_transaction_detected'

    # --- accommodation -------------------------------------------------
    PROPERTY_SUBMITTED = 'property.submitted'
    PROPERTY_APPROVED = 'property.approved'
    PROPERTY_REJECTED = 'property.rejected'
    PROPERTY_CHANGES_REQUESTED = 'property.changes_requested'
    PROPERTY_SUSPENDED = 'property.suspended'
    PROPERTY_REINSTATED = 'property.reinstated'
    REVIEW_RECEIVED = 'review.received'

    # --- bookings (shared across accommodation/transport/tourism) ------
    BOOKING_CREATED = 'booking.created'
    BOOKING_CONFIRMED = 'booking.confirmed'
    BOOKING_CANCELLED = 'booking.cancelled'
    BOOKING_CHECKED_IN = 'booking.checked_in'
    BOOKING_CHECKED_OUT = 'booking.checked_out'
    BOOKING_UPDATED = 'booking.updated'

    # --- transport ------------------------------------------------------
    TRANSPORT_BOOKING_CREATED = 'transport.booking_created'
    TRANSPORT_DRIVER_ASSIGNED = 'transport.driver_assigned'
    TRANSPORT_TRIP_STARTED = 'transport.trip_started'
    TRANSPORT_TRIP_COMPLETED = 'transport.trip_completed'

    # --- events (business domain: matches/tickets) ----------------------
    EVENT_REGISTERED = 'event.registered'
    EVENT_REMINDER_DUE = 'event.reminder_due'
    EVENT_CANCELLED = 'event.cancelled'
    EVENT_ACCOMMODATION_ASSIGNED = 'event.accommodation_assigned'
    EVENT_ACCOMMODATION_CHANGED = 'event.accommodation_changed'
    EVENT_TRANSPORT_ASSIGNED = 'event.transport_assigned'
    EVENT_TRANSPORT_CHANGED = 'event.transport_changed'
    EVENT_COORDINATION_CANCELLED = 'event.coordination_cancelled'

    # --- messaging / system ---------------------------------------------
    MESSAGE_SENT = 'message.sent'
    SYSTEM_ALERT_RAISED = 'system.alert_raised'
    PLATFORM_ANNOUNCEMENT_PUBLISHED = 'system.announcement_published'


@dataclass
class EventDefinition:
    """
    Registered contract for one event type.

    ``required_fields`` gives cheap structural validation at publish time so a
    malformed event is rejected by the producer rather than exploding inside a
    consumer hours later.
    """

    event_type: str
    version: int = 1
    description: str = ''
    aggregate_type: Optional[str] = None
    required_fields: List[str] = field(default_factory=list)
    # Marks events that must be retained for compliance/audit purposes.
    audited: bool = True
    # Marks events safe to expose to external partner subscriptions.
    externally_visible: bool = False
    validator: Optional[Callable[[Dict[str, Any]], None]] = None

    def validate(self, payload: Dict[str, Any]) -> None:
        payload = payload or {}
        missing = [f for f in self.required_fields if f not in payload]
        if missing:
            raise EventValidationError(
                f"Event '{self.event_type}' missing required payload "
                f"field(s): {', '.join(sorted(missing))}"
            )
        if self.validator is not None:
            self.validator(payload)


class EventRegistry:
    """
    Central catalogue of known event types.

    Unknown types are *permitted* but logged — this keeps the platform usable
    during incremental rollout while still surfacing typos. Set
    ``strict=True`` to reject unregistered types outright (recommended in CI).
    """

    def __init__(self, strict: bool = False):
        self._definitions: Dict[str, EventDefinition] = {}
        self.strict = strict

    def register(self, definition: EventDefinition) -> EventDefinition:
        existing = self._definitions.get(definition.event_type)
        if existing and existing.version != definition.version:
            logger.info(
                "Event '%s' re-registered: v%s -> v%s",
                definition.event_type, existing.version, definition.version,
            )
        self._definitions[definition.event_type] = definition
        return definition

    def get(self, event_type: str) -> Optional[EventDefinition]:
        return self._definitions.get(event_type)

    def require(self, event_type: str) -> EventDefinition:
        definition = self._definitions.get(event_type)
        if definition is None:
            raise UnknownEventTypeError(f"Event type '{event_type}' is not registered")
        return definition

    def validate(self, event_type: str, payload: Dict[str, Any], version: int = 1) -> int:
        """
        Validate *payload* for *event_type*.

        Returns the version to stamp on the event (the registered version when
        the caller did not override it).
        """
        definition = self._definitions.get(event_type)
        if definition is None:
            if self.strict:
                raise UnknownEventTypeError(
                    f"Event type '{event_type}' is not registered "
                    f"(registry is in strict mode)"
                )
            logger.warning(
                "Publishing unregistered event type '%s'. Add it to EventRegistry.",
                event_type,
            )
            return version
        definition.validate(payload)
        return version if version and version != 1 else definition.version

    def is_externally_visible(self, event_type: str) -> bool:
        definition = self._definitions.get(event_type)
        return bool(definition and definition.externally_visible)

    def all(self) -> Dict[str, EventDefinition]:
        return dict(self._definitions)

    def types(self) -> Set[str]:
        return set(self._definitions)


event_registry = EventRegistry()


def register_event(
    event_type: str,
    version: int = 1,
    description: str = '',
    aggregate_type: Optional[str] = None,
    required_fields: Optional[List[str]] = None,
    audited: bool = True,
    externally_visible: bool = False,
    validator: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> EventDefinition:
    """Register an event contract on the global registry."""
    return event_registry.register(
        EventDefinition(
            event_type=event_type,
            version=version,
            description=description,
            aggregate_type=aggregate_type,
            required_fields=list(required_fields or []),
            audited=audited,
            externally_visible=externally_visible,
            validator=validator,
        )
    )


def _bootstrap_registry() -> None:
    """Register the built-in AFCON360 event catalogue."""
    E = EventType

    # identity / account
    register_event(E.USER_REGISTERED, 1, 'A new user account was created',
                   'user', ['user_id'], externally_visible=False)
    register_event(E.USER_EMAIL_VERIFIED, 1, 'User verified their email', 'user', ['user_id'])
    register_event(E.USER_PROFILE_UPDATED, 1, 'User profile changed', 'user', ['user_id'])
    register_event(E.USER_DEACTIVATED, 1, 'User account deactivated', 'user', ['user_id'])
    register_event(E.USER_REACTIVATED, 1, 'User account reactivated', 'user', ['user_id'])

    # security
    register_event(E.LOGIN_SUCCEEDED, 1, 'Successful authentication', 'session', ['user_id'])
    register_event(E.LOGIN_FAILED, 1, 'Failed authentication attempt', 'session')
    register_event(E.PASSWORD_CHANGED, 1, 'Password changed', 'user', ['user_id'])
    register_event(E.PASSWORD_RESET_REQUESTED, 1, 'Password reset requested', 'user')
    register_event(E.MFA_ENABLED, 1, 'MFA enabled', 'user', ['user_id'])
    register_event(E.MFA_DISABLED, 1, 'MFA disabled', 'user', ['user_id'])
    register_event(E.MFA_FAILED, 1, 'MFA challenge failed', 'user', ['user_id'])
    register_event(E.SESSION_REVOKED, 1, 'Session revoked', 'session', ['user_id'])
    register_event(E.DEVICE_REGISTERED, 1, 'New device registered', 'device', ['user_id'])
    register_event(E.API_KEY_CREATED, 1, 'API key created', 'api_key', ['user_id'])
    register_event(E.API_KEY_REVOKED, 1, 'API key revoked', 'api_key', ['user_id'])
    register_event(E.ADMIN_LOGIN, 1, 'Administrator signed in', 'session', ['user_id'])
    register_event(E.ADMIN_ACTION, 1, 'Administrator performed an action', 'admin')
    register_event(E.PERMISSION_CHANGED, 1, 'Permission grant changed', 'user', ['user_id'])
    register_event(E.ROLE_CHANGED, 1, 'Role assignment changed', 'user', ['user_id'])
    register_event(E.SUSPICIOUS_ACTIVITY, 1, 'Risk engine flagged activity', 'user')

    # kyc
    register_event(E.KYC_SUBMITTED, 1, 'KYC documents submitted', 'kyc', ['user_id'])
    register_event(E.KYC_REVIEW_STARTED, 1, 'Compliance began review', 'kyc', ['user_id'])
    register_event(E.KYC_APPROVED, 1, 'KYC approved', 'kyc', ['user_id'])
    register_event(E.KYC_REJECTED, 1, 'KYC rejected', 'kyc', ['user_id'])
    register_event(E.KYC_EXPIRED, 1, 'KYC verification expired', 'kyc', ['user_id'])

    # wallet / payments
    register_event(E.WALLET_CREATED, 1, 'Wallet provisioned', 'wallet', ['user_id'])
    register_event(E.PAYMENT_INITIATED, 1, 'Payment started', 'payment', ['user_id'])
    register_event(E.PAYMENT_PENDING, 1, 'Payment awaiting provider', 'payment', ['user_id'])
    register_event(E.PAYMENT_SUCCESSFUL, 1, 'Payment captured', 'payment',
                   ['user_id', 'amount'], externally_visible=True)
    register_event(E.PAYMENT_FAILED, 1, 'Payment failed', 'payment', ['user_id'],
                   externally_visible=True)
    register_event(E.PAYMENT_REFUNDED, 1, 'Payment refunded', 'payment', ['user_id'],
                   externally_visible=True)
    register_event(E.DEPOSIT_CONFIRMED, 1, 'Wallet deposit confirmed', 'transaction', ['user_id'])
    register_event(E.WITHDRAWAL_COMPLETED, 1, 'Wallet withdrawal completed', 'transaction', ['user_id'])
    register_event(E.TRANSACTION_COMPLETED, 1, 'Wallet transaction settled', 'transaction', ['user_id'])
    register_event(E.LARGE_TRANSACTION_DETECTED, 1, 'Transaction exceeded threshold',
                   'transaction', ['user_id', 'amount'])

    # accommodation
    register_event(E.PROPERTY_SUBMITTED, 1, 'Property submitted for review', 'property')
    register_event(E.PROPERTY_APPROVED, 1, 'Property approved', 'property',
                   externally_visible=True)
    register_event(E.PROPERTY_REJECTED, 1, 'Property rejected', 'property')
    register_event(E.PROPERTY_CHANGES_REQUESTED, 1, 'Changes requested on property', 'property')
    register_event(E.PROPERTY_SUSPENDED, 1, 'Property suspended', 'property')
    register_event(E.PROPERTY_REINSTATED, 1, 'Property reinstated', 'property')
    register_event(E.REVIEW_RECEIVED, 1, 'Review left on a property', 'review')

    # bookings
    register_event(E.BOOKING_CREATED, 1, 'Booking created', 'booking', externally_visible=True)
    register_event(E.BOOKING_CONFIRMED, 1, 'Booking confirmed', 'booking',
                   externally_visible=True)
    register_event(E.BOOKING_CANCELLED, 1, 'Booking cancelled', 'booking',
                   externally_visible=True)
    register_event(E.BOOKING_CHECKED_IN, 1, 'Guest checked in', 'booking')
    register_event(E.BOOKING_CHECKED_OUT, 1, 'Guest checked out', 'booking')
    register_event(E.BOOKING_UPDATED, 1, 'Booking details changed', 'booking')

    # transport
    register_event(E.TRANSPORT_BOOKING_CREATED, 1, 'Transport booking created', 'booking')
    register_event(E.TRANSPORT_DRIVER_ASSIGNED, 1, 'Driver assigned to trip', 'booking')
    register_event(E.TRANSPORT_TRIP_STARTED, 1, 'Trip started', 'booking')
    register_event(E.TRANSPORT_TRIP_COMPLETED, 1, 'Trip completed', 'booking')

    # events domain
    register_event(E.EVENT_REGISTERED, 1, 'User registered for an event',
                   'event_registration', externally_visible=True)
    register_event(E.EVENT_REMINDER_DUE, 1, 'Event reminder is due', 'event')
    register_event(E.EVENT_CANCELLED, 1, 'Event cancelled', 'event', externally_visible=True)
    register_event(E.EVENT_ACCOMMODATION_ASSIGNED, 1, 'Accommodation coordinated for attendee',
                   'event_assignment', ['event_ref', 'registration_ref'])
    register_event(E.EVENT_ACCOMMODATION_CHANGED, 1, 'Accommodation coordination changed',
                   'event_assignment', ['event_ref', 'registration_ref', 'previous_booking_ref', 'booking_ref'])
    register_event(E.EVENT_TRANSPORT_ASSIGNED, 1, 'Transport coordinated for attendee',
                   'event_assignment', ['event_ref', 'registration_ref'])
    register_event(E.EVENT_TRANSPORT_CHANGED, 1, 'Transport coordination changed',
                   'event_assignment', ['event_ref', 'registration_ref', 'previous_booking_ref', 'booking_ref'])
    register_event(E.EVENT_COORDINATION_CANCELLED, 1, 'Event coordination assignment cancelled',
                   'event_assignment', ['event_ref', 'registration_ref', 'capability'])

    # messaging / system
    register_event(E.MESSAGE_SENT, 1, 'Internal message sent', 'message')
    register_event(E.SYSTEM_ALERT_RAISED, 1, 'Operational alert raised', 'system')
    register_event(E.PLATFORM_ANNOUNCEMENT_PUBLISHED, 1, 'Platform announcement', 'system')


_bootstrap_registry()
