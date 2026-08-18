"""
Notification Policy Engine.

This is the "brain" the spec asks for: it answers, for a given domain event,

    Is a notification required?
    Who receives it?
    Which channels?
    Is the user allowed to opt out?
    What priority?
    Does a threshold escalate it to another role?

…declaratively, in one table, instead of being scattered across
``send_wallet_notification`` / ``send_booking_notification`` / etc.

Two concepts that must not be confused
--------------------------------------
* :class:`DeliveryClass` — *governance*. MANDATORY (security alerts, payment
  receipts, legal notices) cannot be switched off by a user; OPTIONAL respects
  preferences; MARKETING additionally requires explicit opt-in. This is what
  stops a user from disabling their own fraud alerts.
* :class:`Audience` — *targeting*. The subject of the event, a fixed role set,
  or a threshold-gated escalation.

Relationship to the existing service
------------------------------------
The policy engine RESOLVES intent into concrete directives; it does not send.
Actual delivery still goes through ``NotificationService`` and the single
``EmailHandler``, so the ADR's "one entry point, one sender" rule is preserved.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .registry import EventType
from .schemas import EventEnvelope

logger = logging.getLogger(__name__)


class DeliveryClass(str, enum.Enum):
    """How much control the user has over receiving this."""
    MANDATORY = 'mandatory'   # security/financial/legal — cannot be disabled
    OPTIONAL = 'optional'     # respects UserNotificationPreference
    MARKETING = 'marketing'   # requires explicit opt-in


class Audience(str, enum.Enum):
    """Who a directive targets."""
    SUBJECT = 'subject'   # the user the event is about
    ROLES = 'roles'       # operational staff (wallet_admin, compliance, ...)
    ACTOR = 'actor'       # whoever triggered the event
    CUSTOM = 'custom'     # resolved by a callable on the rule


@dataclass
class NotificationDirective:
    """One concrete "send this to these people" instruction."""
    audience: Audience
    notification_type: str
    title: str
    message: str
    channels: List[str] = field(default_factory=lambda: ['in_app'])
    priority: str = 'normal'
    delivery_class: DeliveryClass = DeliveryClass.OPTIONAL
    module: Optional[str] = None
    link: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    user_ids: List[int] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)

    @property
    def force_external(self) -> bool:
        """
        MANDATORY notifications bypass the opt-in requirement for external
        channels — a payment receipt must reach the real mailbox.
        """
        return self.delivery_class == DeliveryClass.MANDATORY


@dataclass
class NotificationPolicy:
    """
    Declarative mapping from an event type to notification directives.

    ``condition`` and ``threshold`` allow the same event to behave differently
    based on payload — e.g. every payment notifies the owner, but only payments
    over a threshold also page compliance.
    """
    event_type: str
    notification_type: str
    title: str
    message: str
    channels: List[str] = field(default_factory=lambda: ['in_app'])
    priority: str = 'normal'
    delivery_class: DeliveryClass = DeliveryClass.OPTIONAL
    module: Optional[str] = None
    link: Optional[str] = None
    audience: Audience = Audience.SUBJECT
    roles: List[str] = field(default_factory=list)
    condition: Optional[Callable[[EventEnvelope], bool]] = None
    resolver: Optional[Callable[[EventEnvelope], Sequence[int]]] = None
    enabled: bool = True

    def applies_to(self, envelope: EventEnvelope) -> bool:
        if not self.enabled:
            return False
        if self.condition is None:
            return True
        try:
            return bool(self.condition(envelope))
        except Exception as exc:
            logger.warning(
                "Policy condition failed for %s/%s: %s",
                self.event_type, self.notification_type, exc,
            )
            return False

    def render(self, envelope: EventEnvelope) -> NotificationDirective:
        """Interpolate the event payload into the copy and link."""
        ctx = dict(envelope.payload or {})
        ctx.setdefault('event_type', envelope.event_type)

        def fmt(template: Optional[str]) -> Optional[str]:
            if not template:
                return template
            try:
                return template.format(**ctx)
            except Exception:
                # Missing key: emit the raw template rather than crashing.
                return template

        user_ids: List[int] = []
        if self.resolver is not None:
            try:
                user_ids = [int(u) for u in (self.resolver(envelope) or [])]
            except Exception as exc:
                logger.warning("Policy resolver failed for %s: %s", self.event_type, exc)

        return NotificationDirective(
            audience=self.audience,
            notification_type=self.notification_type,
            title=fmt(self.title) or '',
            message=fmt(self.message) or '',
            channels=list(self.channels),
            priority=self.priority,
            delivery_class=self.delivery_class,
            module=self.module or ctx.get('module'),
            link=fmt(self.link),
            roles=list(self.roles),
            user_ids=user_ids,
            data=ctx,
        )


class PolicyEngine:
    """Registry + evaluator for notification policies."""

    def __init__(self):
        self._policies: Dict[str, List[NotificationPolicy]] = {}

    def register(self, policy: NotificationPolicy) -> NotificationPolicy:
        self._policies.setdefault(policy.event_type, []).append(policy)
        return policy

    def register_many(self, policies: Sequence[NotificationPolicy]) -> None:
        for policy in policies:
            self.register(policy)

    def policies_for(self, event_type: str) -> List[NotificationPolicy]:
        return list(self._policies.get(event_type, []))

    def resolve(self, envelope: EventEnvelope) -> List[NotificationDirective]:
        """
        Turn an event into the set of notifications it should produce.

        Returns an empty list when the event is not notification-worthy — many
        events exist purely for audit/analytics, which is exactly the
        separation the architecture requires.
        """
        directives: List[NotificationDirective] = []
        for policy in self._policies.get(envelope.event_type, []):
            if policy.applies_to(envelope):
                directives.append(policy.render(envelope))
        return directives

    def all(self) -> Dict[str, List[NotificationPolicy]]:
        return {k: list(v) for k, v in self._policies.items()}


policy_engine = PolicyEngine()


# ----------------------------------------------------------------------
# Threshold helpers
# ----------------------------------------------------------------------
LARGE_TRANSACTION_THRESHOLD = 1_000_000  # UGX


def _amount_over(threshold: float) -> Callable[[EventEnvelope], bool]:
    def _check(envelope: EventEnvelope) -> bool:
        try:
            return float(envelope.get('amount') or 0) >= threshold
        except (TypeError, ValueError):
            return False
    return _check


def _bootstrap_policies() -> None:
    """
    Default AFCON360 notification policy set.

    Read this as the platform's communication contract: each entry states an
    event, who hears about it, on which channels, and whether the user may
    silence it.
    """
    E = EventType
    P = NotificationPolicy

    policy_engine.register_many([
        # ---------------- account lifecycle ----------------
        P(event_type=E.USER_REGISTERED,
          notification_type='signup_notification',
          title='Welcome to AFCON360',
          message='Your account has been created successfully. Explore accommodation, transport and events.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, module='account', link='/dashboard'),
        P(event_type=E.USER_REGISTERED,
          notification_type='admin_notification',
          title='New user registration',
          message='A new user account was created on the platform.',
          channels=['in_app'], priority='low', audience=Audience.ROLES,
          roles=['owner', 'super_admin', 'admin', 'support'],
          module='account', link='/admin/users'),

        # ---------------- security (mandatory) ----------------
        P(event_type=E.PASSWORD_CHANGED,
          notification_type='login_alert',
          title='Your password was changed',
          message='Your AFCON360 password was just changed. If this was not you, contact support immediately.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, module='account'),
        P(event_type=E.LOGIN_SUCCEEDED,
          notification_type='login_alert',
          title='New sign-in to your account',
          message='A new sign-in was detected on your account.',
          channels=['in_app'], priority='low', module='account',
          condition=lambda e: bool(e.get('new_device'))),
        P(event_type=E.SUSPICIOUS_ACTIVITY,
          notification_type='system_alert',
          title='Suspicious activity detected',
          message='Unusual activity was detected on your account and is under review.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, module='account'),
        P(event_type=E.SUSPICIOUS_ACTIVITY,
          notification_type='system_alert',
          title='Risk engine alert',
          message='Suspicious activity flagged for review.',
          channels=['in_app'], priority='high', audience=Audience.ROLES,
          roles=['compliance_officer', 'auditor', 'super_admin'],
          module='system', link='/admin/compliance'),

        # ---------------- KYC ----------------
        P(event_type=E.KYC_SUBMITTED,
          notification_type='admin_notification',
          title='KYC submission awaiting review',
          message='A new KYC submission requires manual review.',
          channels=['in_app'], priority='normal', audience=Audience.ROLES,
          roles=['compliance_officer', 'auditor', 'super_admin', 'admin'],
          module='kyc', link='/admin/compliance/kyc-queue'),
        P(event_type=E.KYC_APPROVED,
          notification_type='kyc_approved',
          title='Your identity has been verified',
          message='Congratulations — your KYC verification is approved. Full platform features are now unlocked.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, module='kyc', link='/profile/kyc'),
        P(event_type=E.KYC_REJECTED,
          notification_type='kyc_rejected',
          title='Additional information needed',
          message='Your KYC verification requires additional information. Please review and resubmit.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, module='kyc', link='/profile/kyc'),

        # ---------------- wallet / payments ----------------
        P(event_type=E.WALLET_CREATED,
          notification_type='system_alert',
          title='Your wallet is ready',
          message='Your AFCON360 wallet has been created and is ready to use.',
          channels=['in_app'], priority='normal', module='wallet', link='/wallet'),
        P(event_type=E.PAYMENT_SUCCESSFUL,
          notification_type='payment_received',
          title='Payment successful',
          message='Your payment of {currency} {amount} was successful.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, module='wallet', link='/wallet/transactions'),
        P(event_type=E.PAYMENT_FAILED,
          notification_type='system_alert',
          title='Payment failed',
          message='Your payment of {currency} {amount} could not be completed.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, module='wallet', link='/wallet/transactions'),
        P(event_type=E.DEPOSIT_CONFIRMED,
          notification_type='deposit_confirmed',
          title='Deposit confirmed',
          message='{currency} {amount} has been credited to your wallet.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, module='wallet', link='/wallet'),
        P(event_type=E.WITHDRAWAL_COMPLETED,
          notification_type='withdrawal_completed',
          title='Withdrawal completed',
          message='{currency} {amount} has been withdrawn from your wallet.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, module='wallet', link='/wallet'),
        # Threshold escalation — only large payments page compliance.
        P(event_type=E.PAYMENT_SUCCESSFUL,
          notification_type='system_alert',
          title='Large transaction recorded',
          message='A transaction of {currency} {amount} exceeded the monitoring threshold.',
          channels=['in_app'], priority='high', audience=Audience.ROLES,
          roles=['wallet_admin', 'compliance_officer', 'auditor'],
          module='wallet', link='/admin/wallet-admin-dashboard',
          condition=_amount_over(LARGE_TRANSACTION_THRESHOLD)),
        P(event_type=E.LARGE_TRANSACTION_DETECTED,
          notification_type='system_alert',
          title='Large transaction flagged',
          message='A transaction of {currency} {amount} was flagged for review.',
          channels=['in_app'], priority='high', audience=Audience.ROLES,
          roles=['wallet_admin', 'compliance_officer', 'auditor', 'super_admin'],
          module='wallet', link='/admin/wallet-admin-dashboard'),

        # ---------------- bookings ----------------
        P(event_type=E.BOOKING_CONFIRMED,
          notification_type='booking_confirmed',
          title='Booking confirmed',
          message='Your booking {booking_reference} has been confirmed.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, link='/accommodation/bookings'),
        P(event_type=E.BOOKING_CANCELLED,
          notification_type='booking_cancelled',
          title='Booking cancelled',
          message='Your booking {booking_reference} has been cancelled.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, link='/accommodation/bookings'),
        P(event_type=E.BOOKING_CREATED,
          notification_type='admin_notification',
          title='New booking received',
          message='A new booking {booking_reference} was created.',
          channels=['in_app'], priority='normal', audience=Audience.ROLES,
          roles=['accommodation_admin', 'moderator', 'admin'],
          link='/accommodation/admin/bookings'),

        # ---------------- accommodation ----------------
        P(event_type=E.PROPERTY_SUBMITTED,
          notification_type='admin_notification',
          title='Property awaiting moderation',
          message='A new property was submitted and needs review.',
          channels=['in_app'], priority='normal', audience=Audience.ROLES,
          roles=['accommodation_admin', 'moderator', 'admin', 'super_admin'],
          module='accommodation', link='/accommodation/admin/moderation'),
        P(event_type=E.PROPERTY_APPROVED,
          notification_type='property_approved',
          title='Your property was approved',
          message='Your property listing is now live on AFCON360.',
          channels=['in_app', 'email'], priority='high',
          module='accommodation', link='/accommodation/host/properties'),
        P(event_type=E.PROPERTY_REJECTED,
          notification_type='property_rejected',
          title='Your property needs changes',
          message='Your property listing was not approved. Please review the feedback.',
          channels=['in_app', 'email'], priority='high',
          module='accommodation', link='/accommodation/host/properties'),
        P(event_type=E.REVIEW_RECEIVED,
          notification_type='review_received',
          title='New review received',
          message='You received a new review on your property.',
          channels=['in_app'], priority='normal', module='accommodation'),

        # ---------------- transport ----------------
        P(event_type=E.TRANSPORT_DRIVER_ASSIGNED,
          notification_type='driver_assigned',
          title='Driver assigned',
          message='A driver has been assigned to your trip.',
          channels=['in_app', 'email'], priority='high',
          module='transport', link='/transport/bookings'),
        P(event_type=E.TRANSPORT_BOOKING_CREATED,
          notification_type='admin_notification',
          title='New transport booking',
          message='A new transport booking was created.',
          channels=['in_app'], priority='normal', audience=Audience.ROLES,
          roles=['transport_admin', 'admin'],
          module='transport', link='/transport/admin/dashboard'),

        # ---------------- events domain ----------------
        P(event_type=E.EVENT_REGISTERED,
          notification_type='event_registered',
          title='Registration confirmed',
          message='You are registered. Your confirmation details are attached.',
          channels=['in_app', 'email'], priority='high',
          delivery_class=DeliveryClass.MANDATORY, module='events', link='/events'),
        P(event_type=E.EVENT_REGISTERED,
          notification_type='admin_notification',
          title='New event registration',
          message='A new registration was received.',
          channels=['in_app'], priority='low', audience=Audience.ROLES,
          roles=['event_manager', 'admin'], module='events',
          link='/events/admin/dashboard'),
        P(event_type=E.EVENT_REMINDER_DUE,
          notification_type='event_reminder',
          title='Your event is coming up',
          message='This is a reminder about your upcoming event.',
          channels=['in_app', 'email'], priority='normal', module='events'),
        P(event_type=E.EVENT_ACCOMMODATION_ASSIGNED,
          notification_type='event_accommodation_assigned',
          title='Accommodation assigned',
          message='Accommodation has been assigned for event {event_ref}.',
          channels=['in_app', 'email'], priority='high', module='events',
          link='/events/{event_ref}'),
        P(event_type=E.EVENT_ACCOMMODATION_CHANGED,
          notification_type='event_accommodation_changed',
          title='Accommodation assignment changed',
          message='Your accommodation assignment for event {event_ref} has changed.',
          channels=['in_app', 'email'], priority='high', module='events',
          link='/events/{event_ref}'),
        P(event_type=E.EVENT_TRANSPORT_ASSIGNED,
          notification_type='event_transport_assigned',
          title='Transport assigned',
          message='Transport has been assigned for event {event_ref}.',
          channels=['in_app', 'email'], priority='high', module='events',
          link='/events/{event_ref}'),
        P(event_type=E.EVENT_TRANSPORT_CHANGED,
          notification_type='event_transport_changed',
          title='Transport assignment changed',
          message='Your transport assignment for event {event_ref} has changed.',
          channels=['in_app', 'email'], priority='high', module='events',
          link='/events/{event_ref}'),
        P(event_type=E.EVENT_COORDINATION_CANCELLED,
          notification_type='event_coordination_cancelled',
          title='Event assignment cancelled',
          message='Your {capability} assignment for event {event_ref} was cancelled.',
          channels=['in_app', 'email'], priority='high', module='events',
          link='/events/{event_ref}'),

        # ---------------- messaging / system ----------------
        P(event_type=E.MESSAGE_SENT,
          notification_type='message_notification',
          title='New message',
          message='You have received a new message.',
          channels=['in_app'], priority='normal', module='messaging',
          link='/api/notifications/messages'),
        P(event_type=E.PLATFORM_ANNOUNCEMENT_PUBLISHED,
          notification_type='platform_announcement',
          title='{title}',
          message='{body}',
          channels=['in_app'], priority='normal', module='system'),
    ])


_bootstrap_policies()
