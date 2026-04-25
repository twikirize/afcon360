# app/events/services.py
"""
Event Service — DB-backed event management.
Synchronized with constants.py (single source of truth) and models.py (state machine).

Changes over v2
───────────────
1.  create_event     — KYC-aware auto-approve + auto-publish on submission
2.  approve_event    — correctly transitions to APPROVED (not PUBLISHED)
3.  publish_event    — new method; organiser or admin publishes from APPROVED
4.  change_event_status — actor permission guard before model delegation
5.  get_event_stats  — SQL aggregation, no Python row iteration
6.  get_admin_dashboard_data  — single GROUP BY replaces 9 COUNT queries
7.  get_organizer_dashboard_data — single GROUP BY replaces N+1 loop
8.  get_attendee_dashboard_data — joinedload, no per-row Event.query.get()
9.  _registration_to_dict — uses registration.event relationship (no extra query)
10. _ticket_type_to_dict  — COUNT removed; callers pass pre-fetched counts
11. _event_to_dict        — receives optional reg_counts map for ticket types
"""

from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple
import logging
import re
import qrcode
import functools
import hashlib
from io import BytesIO
import base64
from flask import current_app
from app.extensions import db, redis_client
from app.events.models import (
    Event, TicketType, EventRegistration, EventRole,
    Waitlist, EventAssignment,
)
from app.events.constants import (
    EventStatus,
    ALLOWED_TRANSITIONS,
    validate_transition,
    PUBLIC_VISIBLE_STATUSES,
    REGISTRATION_OPEN_STATUSES,
    TERMINAL_STATUSES,
    ORGANISER_VISIBLE_STATUSES,
)
from sqlalchemy import func, case, and_
from sqlalchemy.orm import joinedload, subqueryload
from decimal import Decimal

logger = logging.getLogger(__name__)


# ============================================================================
# MODULE INDEPENDENCE
# ============================================================================

MODULES_AVAILABLE = {
    'accommodation': False,
    'transport': False,
    'wallet': False,
    'audit': False,
}

try:
    from app.accommodation.models.booking import AccommodationBooking, BookingContextType
    MODULES_AVAILABLE['accommodation'] = True
except ImportError:
    from enum import Enum
    class BookingContextType(Enum):
        EVENT = "event"
        TOURISM = "tourism"
        TRANSPORT = "transport"
        GENERAL = "general"
    AccommodationBooking = None

try:
    from app.transport.models import Booking as TransportBooking
    MODULES_AVAILABLE['transport'] = True
except ImportError:
    TransportBooking = None

try:
    from app.wallet.services.wallet_service import WalletService
    MODULES_AVAILABLE['wallet'] = True
except ImportError:
    WalletService = None
    logger.warning("WalletService not available — wallet features limited")

try:
    from app.audit.comprehensive_audit import AuditService
    MODULES_AVAILABLE['audit'] = True
except ImportError:
    AuditService = None


# ============================================================================
# SIGNALS
# ============================================================================

try:
    from app.events.signal_handlers import (
        event_registered,
        event_cancelled,
        event_capacity_released,
        offer_services_after_registration,
        service_provider_data_requested,
    )
    SIGNALS_AVAILABLE = True
except ImportError:
    SIGNALS_AVAILABLE = False
    logger.warning("Signals not available — loose coupling features limited")


# ============================================================================
# UTILITIES
# ============================================================================

def sanitize_status(status_value):
    """Convert any status value to a valid EventStatus string."""
    if status_value is None:
        return EventStatus.DRAFT.value
    if isinstance(status_value, EventStatus):
        return status_value.value
    try:
        return EventStatus(str(status_value)).value
    except ValueError:
        logger.warning(f"Legacy status '{status_value}' — defaulting to DRAFT")
        return EventStatus.DRAFT.value


class SoldOutException(Exception):
    """Raised when event or ticket type is at capacity."""
    pass


class IdempotencyChecker:
    """Prevents duplicate request processing."""

    @staticmethod
    def check_and_store(key: str, ttl_seconds: int = 300) -> bool:
        if not redis_client:
            return False
        result = redis_client.set(f"idempotency:{key}", "1", nx=True, ex=ttl_seconds)
        return result is not True

    @staticmethod
    def generate_key(user_id: int, identifier: str, data_hash: str) -> str:
        return hashlib.sha256(f"{user_id}:{identifier}:{data_hash}".encode()).hexdigest()


def with_transaction(isolation_level="REPEATABLE_READ"):
    """Decorator for database transaction management."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if db.session.is_active:
                return func(*args, **kwargs)
            try:
                with db.session.begin_nested():
                    return func(*args, **kwargs)
            except Exception as e:
                db.session.rollback()
                logger.error(f"Transaction failed in {func.__name__}: {e}")
                raise
        return wrapper
    return decorator


# ============================================================================
# KYC HELPER
# ============================================================================

def _is_kyc_verified(user, organization_id: int = None) -> bool:
    """
    Return True if the organiser is KYC-verified.

    For individual events:   check user.kyc_verified
    For organisation events: check the org's kyc_verified flag
    Falls back to False on any attribute error so unverified is the safe default.
    """
    try:
        if organization_id:
            from app.identity.models.organisation import Organisation
            org = Organisation.query.get(organization_id)
            return bool(org and getattr(org, 'kyc_verified', False))
        return bool(getattr(user, 'kyc_verified', False))
    except Exception:
        return False


def _compute_risk_flags(user, data: Dict, organization_id: int = None) -> List[str]:
    """
    Lightweight risk signal list attached to the event at submission time.
    Admins see these during moderation. Never shown to organisers.
    Extend this list as needed — it never blocks submission.
    """
    flags = []
    try:
        account_age = (datetime.utcnow() - user.created_at).days if user.created_at else 0
        if account_age < 30:
            flags.append("new_account")
        if not getattr(user, 'phone_verified', False):
            flags.append("unverified_phone")
        if not getattr(user, 'email_verified', False):
            flags.append("unverified_email")

        # Event-level signals
        if data.get("start_date"):
            start = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
            if (start - date.today()).days < 3:
                flags.append("very_short_notice")
        if not data.get("venue"):
            flags.append("no_venue")
        if not data.get("contact_email") and not data.get("contact_phone"):
            flags.append("no_contact_info")
    except Exception:
        pass
    return flags


# ============================================================================
# CROSS-SELLING SERVICE
# ============================================================================

class CrossSellingService:
    """Recommends accommodation/transport based on attendee profile."""

    @staticmethod
    def analyze_attendee_needs(user_city: str, user_country: str, event) -> Dict[str, bool]:
        """
        Accepts plain strings (not the user ORM object) to avoid lazy-load
        queries in the registration hot path.
        """
        needs = {'accommodation': False, 'transport': False}
        if not event:
            return needs
        if user_city and event.city and user_city.lower() != event.city.lower():
            needs['transport'] = True
        if user_country and event.country and user_country.lower() != event.country.lower():
            needs['accommodation'] = True
        if event.start_date and event.end_date:
            if (event.end_date - event.start_date).days > 1:
                needs['accommodation'] = True
        return needs


# ============================================================================
# EVENT SERVICE
# ============================================================================

class EventService:
    """Centralized event management — single entry point for all event operations."""

    # ========================================================================
    # STATUS HELPERS
    # ========================================================================

    @classmethod
    def sanitize_status(cls, status_value):
        return sanitize_status(status_value)

    # ── Actor permission guard ────────────────────────────────────────────

    # Actions only admins/moderators may perform
    _ADMIN_ONLY_ACTIONS = {
        EventStatus.APPROVED,
        EventStatus.REJECTED,
        EventStatus.SUSPENDED,
        EventStatus.DELETED,
    }

    # Actions only the event owner (organiser/org) may perform
    _OWNER_ONLY_ACTIONS = {
        EventStatus.PAUSED,
        EventStatus.ARCHIVED,
    }

    # Actions either party may perform
    _SHARED_ACTIONS = {
        EventStatus.PUBLISHED,
        EventStatus.CANCELLED,
        EventStatus.PENDING_APPROVAL,
        EventStatus.DRAFT,
        EventStatus.COMPLETED,   # normally scheduler, but admin can force
    }

    @classmethod
    def _check_actor_permission(
        cls,
        event: Event,
        new_status: EventStatus,
        actor_id: int,
        is_admin: bool,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify that `actor_id` is allowed to push `event` into `new_status`.
        Returns (allowed, error_message).
        """
        is_owner = (
            event.organizer_id == actor_id
            or event.current_owner_id == actor_id
        )

        if new_status in cls._ADMIN_ONLY_ACTIONS and not is_admin:
            return False, f"Only admins can perform '{new_status.value}'"

        if new_status in cls._OWNER_ONLY_ACTIONS and not is_owner and not is_admin:
            return False, f"Only the event owner can perform '{new_status.value}'"

        # publish: respect publish_permission field
        if new_status == EventStatus.PUBLISHED:
            perm = getattr(event, 'publish_permission', 'either')
            if perm == 'self' and not is_owner:
                return False, "Only the organiser may publish this event"
            if perm == 'admin' and not is_admin:
                return False, "Only an admin may publish this event"

        return True, None

    # ── Core status change ────────────────────────────────────────────────

    @classmethod
    def change_event_status(
        cls,
        event_slug: str,
        new_status,
        actor_id: int,
        reason: str = None,
        ip_address: str = None,
        user_agent: str = None,
        is_admin: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Central status-change method.
        1. Resolves the status string to an EventStatus enum.
        2. Checks actor permission.
        3. Delegates to event.transition_to() (model owns all side-effects).
        4. Commits and returns.
        """
        event = cls.get_event_model(event_slug)
        if not event:
            return False, "Event not found"

        if isinstance(new_status, str):
            try:
                new_status = EventStatus(new_status)
            except ValueError:
                return False, f"Invalid status: {new_status}"

        allowed, err = cls._check_actor_permission(event, new_status, actor_id, is_admin)
        if not allowed:
            return False, err

        try:
            log_entry = event.transition_to(new_status, actor_id, reason, ip_address, user_agent)
            db.session.add(log_entry)
            db.session.commit()
            logger.info(
                f"Event '{event.slug}': {log_entry.from_status.value} → "
                f"{log_entry.to_status.value} by actor {actor_id}"
            )
            return True, None
        except ValueError as e:
            return False, str(e)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Status change failed: {e}")
            return False, str(e)

    # ── Named transition methods ──────────────────────────────────────────

    @classmethod
    def approve_event(
        cls,
        event_slug: str,
        admin_id: int,
        reason: str = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Admin approves event → APPROVED.
        If the event has auto_publish_on_approval=True, immediately publishes.
        Does NOT jump straight to PUBLISHED — that is publish_event()'s job.
        """
        ok, err = cls.change_event_status(
            event_slug, EventStatus.APPROVED, admin_id,
            reason=reason, is_admin=True,
        )
        if not ok:
            return False, err

        # Auto-publish if organiser requested it at submission
        event = cls.get_event_model(event_slug)
        if event and getattr(event, 'auto_publish_on_approval', False):
            return cls.publish_event(event_slug, admin_id, is_admin=True)

        return True, None

    @classmethod
    def publish_event(
        cls,
        event_slug: str,
        actor_id: int,
        is_admin: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Move event APPROVED → PUBLISHED.
        Respects publish_permission on the event.
        Can be called by organiser or admin depending on publish_permission.
        """
        return cls.change_event_status(
            event_slug, EventStatus.PUBLISHED, actor_id, is_admin=is_admin,
        )

    @classmethod
    def reject_event(
        cls,
        event_slug: str,
        admin_id: int,
        reason: str = None,
    ) -> Tuple[bool, Optional[str]]:
        """Admin rejects event → REJECTED."""
        return cls.change_event_status(
            event_slug, EventStatus.REJECTED, admin_id,
            reason=reason, is_admin=True,
        )

    @classmethod
    def suspend_event(
        cls,
        event_slug: str,
        admin_id: int,
        reason: str = None,
    ) -> Tuple[bool, Optional[str]]:
        """Admin suspends a live event."""
        return cls.change_event_status(
            event_slug, EventStatus.SUSPENDED, admin_id,
            reason=reason, is_admin=True,
        )

    @classmethod
    def reactivate_event(
        cls,
        event_slug: str,
        admin_id: int,
    ) -> Tuple[bool, Optional[str]]:
        """Admin lifts suspension → PUBLISHED."""
        return cls.change_event_status(
            event_slug, EventStatus.PUBLISHED, admin_id, is_admin=True,
        )

    @classmethod
    def pause_event(cls, event_slug: str, organiser_id: int) -> Tuple[bool, Optional[str]]:
        """Organiser pauses a live event."""
        return cls.change_event_status(event_slug, EventStatus.PAUSED, organiser_id)

    @classmethod
    def resume_event(cls, event_slug: str, organiser_id: int) -> Tuple[bool, Optional[str]]:
        """Organiser resumes a paused event."""
        return cls.change_event_status(event_slug, EventStatus.PUBLISHED, organiser_id)

    @classmethod
    def cancel_event(
        cls,
        event_slug: str,
        actor_id: int,
        is_admin: bool = False,
        reason: str = None,
    ) -> Tuple[bool, Optional[str]]:
        """Organiser or admin cancels an event."""
        return cls.change_event_status(
            event_slug, EventStatus.CANCELLED, actor_id,
            reason=reason, is_admin=is_admin,
        )

    # ========================================================================
    # QUERIES
    # ========================================================================

    @classmethod
    def get_event_model(cls, event_slug: str) -> Optional[Event]:
        return Event.query.filter_by(slug=event_slug).first()

    @classmethod
    def get_event_model_by_id(cls, event_id: int) -> Optional[Event]:
        return Event.query.get(event_id)

    @classmethod
    def get_event(cls, event_slug: str) -> Optional[Dict]:
        event = cls.get_event_model(event_slug)
        return cls._event_to_dict(event) if event else None

    @classmethod
    def get_all_events(cls, status: str = None) -> List[Dict]:
        query = Event.query.filter_by(is_deleted=False).options(
            subqueryload(Event.ticket_types)
        )
        if status:
            query = query.filter_by(status=cls.sanitize_status(status))
        else:
            query = query.filter(
                Event.status.in_([s.value for s in PUBLIC_VISIBLE_STATUSES])
            )
        events = query.order_by(Event.start_date).all()

        # Batch ticket-type registration counts in one query
        reg_counts = cls._fetch_ticket_reg_counts([e.id for e in events])
        return [cls._event_to_dict(e, reg_counts=reg_counts) for e in events]

    @classmethod
    def get_featured_event(cls) -> Optional[Dict]:
        featured = Event.query.filter_by(
            featured=True, status=EventStatus.PUBLISHED, is_deleted=False
        ).options(subqueryload(Event.ticket_types)).first()
        if featured:
            reg_counts = cls._fetch_ticket_reg_counts([featured.id])
            return cls._event_to_dict(featured, reg_counts=reg_counts)

        upcoming = Event.query.filter(
            Event.status == EventStatus.PUBLISHED,
            Event.is_deleted == False,
            Event.start_date >= date.today()
        ).options(subqueryload(Event.ticket_types)).order_by(Event.start_date).first()

        if upcoming:
            reg_counts = cls._fetch_ticket_reg_counts([upcoming.id])
            return cls._event_to_dict(upcoming, reg_counts=reg_counts)
        return None

    @classmethod
    def get_upcoming_events(cls, limit: int = 3, exclude_featured: bool = False) -> List[Dict]:
        events = Event.query.filter(
            Event.status == EventStatus.PUBLISHED,
            Event.is_deleted == False,
            Event.start_date >= date.today()
        ).options(subqueryload(Event.ticket_types)).order_by(Event.start_date).limit(limit + 1).all()

        if exclude_featured:
            featured = cls.get_featured_event()
            if featured:
                events = [e for e in events if e.slug != featured.get('slug')]

        events = events[:limit]
        reg_counts = cls._fetch_ticket_reg_counts([e.id for e in events])
        return [cls._event_to_dict(e, reg_counts=reg_counts) for e in events]

    @classmethod
    def get_events_by_organizer(cls, organizer_id: int) -> List[Dict]:
        events = Event.query.filter_by(
            organizer_id=organizer_id, is_deleted=False
        ).options(subqueryload(Event.ticket_types)).order_by(Event.created_at.desc()).all()
        reg_counts = cls._fetch_ticket_reg_counts([e.id for e in events])
        return [cls._event_to_dict(e, reg_counts=reg_counts) for e in events]

    @classmethod
    def get_events_by_organisation(cls, organisation_id: int) -> List[Dict]:
        events = Event.query.filter_by(
            organization_id=organisation_id, is_deleted=False
        ).options(subqueryload(Event.ticket_types)).order_by(Event.created_at.desc()).all()
        reg_counts = cls._fetch_ticket_reg_counts([e.id for e in events])
        return [cls._event_to_dict(e, reg_counts=reg_counts) for e in events]

    @classmethod
    def get_events_managed_by_user(cls, user_id: int) -> List[Dict]:
        from app.identity.models.user import User
        user = User.query.get(user_id)
        if not user:
            return []

        events = list(Event.query.filter_by(organizer_id=user_id, is_deleted=False).all())
        for membership in user.organisations:
            if user.has_org_role(membership.organisation_id, "org_owner", "org_admin"):
                events.extend(
                    Event.query.filter_by(
                        organization_id=membership.organisation_id, is_deleted=False
                    ).all()
                )

        unique = list({e.id: e for e in events}.values())
        reg_counts = cls._fetch_ticket_reg_counts([e.id for e in unique])
        return [cls._event_to_dict(e, reg_counts=reg_counts) for e in unique]

    # ========================================================================
    # CRUD
    # ========================================================================

    @classmethod
    def create_event(
        cls,
        data: Dict,
        user_id: int,
        creator_type: str = 'individual',
        organization_id: int = None,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Create a new event.

        KYC flow
        ────────
        KYC verified  → status = APPROVED immediately (skip moderation queue)
                        if auto_publish_on_approval=True → status = PUBLISHED
        KYC unverified → status = PENDING_APPROVAL (normal moderation queue)

        Submission preferences (from form data)
        ────────────────────────────────────────
        data['auto_publish_on_approval'] bool  — publish the moment approved
        data['publish_permission']       str   — 'self' | 'admin' | 'either'
        """
        try:
            from app.auth.helpers import has_global_role, has_org_role
            from app.identity.models.user import User

            user = User.query.get(user_id)
            if not user:
                return None, 'User not found'

            # Authorization
            can_create_system = has_global_role(
                user, 'owner', 'super_admin', 'admin', 'event_manager'
            )
            if creator_type == 'system' and not can_create_system:
                return None, 'Only system admins can create system events'
            if creator_type == 'organization':
                if not organization_id:
                    return None, 'Organization ID required'
                if not has_org_role(user, organization_id, 'org_owner', 'org_admin'):
                    return None, 'Not authorized for this organization'

            # Submission preferences from form
            auto_publish = bool(data.get('auto_publish_on_approval', False))
            publish_perm = data.get('publish_permission', 'either')
            if publish_perm not in ('self', 'admin', 'either'):
                publish_perm = 'either'

            # Risk flags (lightweight, never blocks)
            risk_flags = _compute_risk_flags(user, data, organization_id)

            # KYC check determines starting status
            kyc_verified = _is_kyc_verified(user, organization_id)
            is_event_manager = has_global_role(user, 'event_manager')

            approved_at = None
            approved_by_id = None

            if kyc_verified or is_event_manager:
                # Trusted path — skip moderation queue
                if auto_publish:
                    status = EventStatus.PUBLISHED
                else:
                    status = EventStatus.APPROVED
                approved_at = datetime.utcnow()
                approved_by_id = user_id  # self-approved via KYC trust
            else:
                # Unverified path — goes to moderation queue
                status = EventStatus.PENDING_APPROVAL

            # Generate unique slug
            slug = re.sub(r"[^a-z0-9]+", "-", data["name"].lower()).strip("-")
            original_slug = slug
            # Fetch all taken slugs in one query instead of looping
            existing_slugs = {
                row[0] for row in
                db.session.query(Event.slug).filter(
                    Event.slug.like(f"{original_slug}%")
                ).all()
            }
            counter = 1
            while slug in existing_slugs:
                slug = f"{original_slug}-{counter}"
                counter += 1

            organizer_id = organization_id if creator_type == 'organization' else user_id

            event = Event(
                slug=slug,
                name=data["name"],
                description=data.get("description", ""),
                category=data.get("category", "other"),
                city=data["city"],
                country=data.get("country", "Uganda"),
                venue=data.get("venue", ""),
                start_date=datetime.strptime(data["start_date"], "%Y-%m-%d").date()
                           if data.get("start_date") else None,
                end_date=datetime.strptime(data["end_date"], "%Y-%m-%d").date()
                         if data.get("end_date") else None,
                registration_required=data.get("registration_required", False),
                currency=data.get("currency", "USD"),
                organizer_id=organizer_id,
                website=data.get("website"),
                contact_email=data.get("contact_email"),
                contact_phone=data.get("contact_phone"),
                event_metadata=data.get("metadata", {}),
                status=status,
                # Ownership
                created_by_type=creator_type,
                created_by_id=user_id,           # audit FK — was missing in v2
                created_by_entity_id=organization_id if creator_type == 'organization' else user_id,
                organization_id=organization_id if creator_type == 'organization' else None,
                is_system_event=(creator_type == 'system'),
                original_creator_id=user_id,
                current_owner_type=creator_type,
                current_owner_id=organization_id if creator_type == 'organization' else user_id,
                # Approval
                approved_at=approved_at,
                approved_by_id=approved_by_id,
                # Submission preferences (new fields)
                auto_publish_on_approval=auto_publish,
                publish_permission=publish_perm,
                risk_flags=risk_flags,
            )

            event.generate_ref()
            db.session.add(event)
            db.session.flush()

            # Ticket types
            if data.get("registration_required"):
                event_type = data.get("event_type", "free")
                if event_type == "free":
                    db.session.add(TicketType(
                        event_id=event.id,
                        name="Free Admission",
                        price=0,
                        capacity=data.get("max_capacity"),
                        is_active=True,
                    ))
                elif event_type in ("paid", "ticketed") and data.get("ticket_tiers"):
                    for tier in data["ticket_tiers"]:
                        db.session.add(TicketType(
                            event_id=event.id,
                            name=tier["name"],
                            price=tier["price"],
                            capacity=tier["capacity"],
                            is_active=True,
                        ))
                else:
                    db.session.rollback()
                    return None, "Invalid ticket configuration"

            db.session.commit()
            logger.info(
                f"Event created: {event.slug} | status={status.value} | "
                f"kyc={kyc_verified} | auto_publish={auto_publish}"
            )
            return cls._event_to_dict(event), None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating event: {e}")
            return None, str(e)

    @classmethod
    def update_event(cls, event_slug: str, data: Dict, user_id: int) -> Tuple[bool, Optional[str]]:
        event = cls.get_event_model(event_slug)
        if not event:
            return False, "Event not found"
        if event.organizer_id != user_id:
            return False, "Unauthorized"
        try:
            for key in ['name', 'description', 'city', 'venue', 'website',
                        'contact_email', 'contact_phone']:
                if key in data:
                    setattr(event, key, data[key])
            if data.get("start_date"):
                event.start_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
            if data.get("end_date"):
                event.end_date = datetime.strptime(data["end_date"], "%Y-%m-%d").date()
            event.updated_at = datetime.utcnow()
            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            return False, str(e)

    @classmethod
    def delete_event(cls, event_slug: str, user_id: int) -> Tuple[bool, Optional[str]]:
        event = cls.get_event_model(event_slug)
        if not event:
            return False, "Event not found"
        if event.organizer_id != user_id:
            return False, "Unauthorized"
        registrations = EventRegistration.query.filter_by(event_id=event.id).count()
        if registrations > 0:
            return False, f"Cannot delete event with {registrations} existing registrations"
        try:
            log_entry = event.soft_delete(user_id, reason="Organiser deleted")
            db.session.add(log_entry)
            db.session.commit()
            return True, None
        except ValueError as e:
            return False, str(e)

    @classmethod
    def add_ticket_type(
        cls, event_slug: str, data: Dict, user_id: int
    ) -> Tuple[Optional[Dict], Optional[str]]:
        event = cls.get_event_model(event_slug)
        if not event:
            return None, "Event not found"
        if event.organizer_id != user_id:
            return None, "Unauthorized"
        try:
            ticket = TicketType(
                event_id=event.id,
                name=data["name"],
                description=data.get("description"),
                price=data.get("price", 0),
                capacity=data.get("capacity"),
                available_from=datetime.strptime(data["available_from"], "%Y-%m-%dT%H:%M")
                               if data.get("available_from") else None,
                available_until=datetime.strptime(data["available_until"], "%Y-%m-%dT%H:%M")
                                if data.get("available_until") else None,
                is_active=data.get("is_active", True),
            )
            db.session.add(ticket)
            db.session.commit()
            return cls._ticket_type_to_dict(ticket), None
        except Exception as e:
            db.session.rollback()
            return None, str(e)

    # ========================================================================
    # REGISTRATION
    # ========================================================================

    @classmethod
    def register_for_event(cls, identifier: str, user_id: int, data: Dict) -> Tuple[
            Optional[Dict], Optional[str], Optional[str]]:
        return cls.register_for_event_optimistic(identifier, user_id, data)

    @classmethod
    @with_transaction(isolation_level="REPEATABLE_READ")
    def register_for_event_optimistic(
        cls,
        identifier: str,
        user_id: int,
        data: Dict,
        idempotency_key: str = None,
        max_retries: int = 3,
    ) -> Tuple[Optional[Dict], Optional[str], Optional[str]]:
        """Thread-safe registration with optimistic locking."""

        # Idempotency
        if idempotency_key:
            if IdempotencyChecker.check_and_store(idempotency_key):
                event = Event.query.filter_by(slug=identifier).first()
                if event:
                    existing = EventRegistration.query.filter_by(
                        event_id=event.id, user_id=user_id
                    ).first()
                    if existing:
                        qr = cls._generate_qr_code(existing.qr_token, existing.registration_ref)
                        return cls._registration_to_dict(existing), qr, "Already registered"
                return None, None, "Duplicate request"

        if not idempotency_key:
            data_hash = hashlib.sha256(str(sorted(data.items())).encode()).hexdigest()
            idempotency_key = IdempotencyChecker.generate_key(user_id, identifier, data_hash)

        for attempt in range(max_retries):
            try:
                event = Event.query.filter_by(slug=identifier, is_deleted=False).first()
                if not event:
                    return None, None, "Event not found"
                if not event.accepts_registrations:
                    return None, None, f"Event not accepting registrations ({event.status.value})"

                # Ticket type
                ticket_type_id = data.get("ticket_type_id")
                if ticket_type_id:
                    ticket_type = TicketType.query.filter_by(
                        id=ticket_type_id, event_id=event.id, is_active=True
                    ).first()
                    if not ticket_type:
                        return None, None, "Invalid ticket type"
                else:
                    ticket_type = TicketType.query.filter_by(
                        event_id=event.id, is_active=True
                    ).order_by(TicketType.price.asc()).first()
                    if not ticket_type:
                        return None, None, "No ticket types available"

                # Discount
                discount_amount = Decimal("0.00")
                if data.get("discount_code"):
                    discount, err = cls.validate_discount_code(
                        identifier, data["discount_code"], ticket_type_id
                    )
                    if err:
                        return None, None, f"Discount error: {err}"
                    if discount:
                        discount_amount = discount

                # Atomic seat reservation
                if ticket_type.capacity and ticket_type.capacity > 0:
                    updated = db.session.query(TicketType).filter(
                        and_(
                            TicketType.id == ticket_type.id,
                            func.coalesce(TicketType.available_seats, ticket_type.capacity) > 0,
                        )
                    ).update({
                        'available_seats': func.coalesce(
                            TicketType.available_seats, ticket_type.capacity
                        ) - 1,
                        'version': TicketType.version + 1,
                    })
                    if updated == 0:
                        raise SoldOutException(f"'{ticket_type.name}' is sold out")

                # Event-level capacity
                if event.max_capacity > 0:
                    count = db.session.query(
                        func.count(EventRegistration.id)
                    ).filter_by(event_id=event.id).scalar()
                    if count >= event.max_capacity:
                        raise SoldOutException("Event at full capacity")

                # Duplicate check
                if EventRegistration.query.filter_by(
                    event_id=event.id, user_id=user_id
                ).first():
                    return None, None, "Already registered"

                fee = float(ticket_type.price)
                registration = EventRegistration(
                    event_id=event.id,
                    user_id=user_id,
                    ticket_type_id=ticket_type.id,
                    full_name=data.get("full_name", "").strip(),
                    email=data.get("email", "").strip().lower(),
                    phone=data.get("phone", "").strip(),
                    nationality=data.get("nationality", "").strip(),
                    id_number=data.get("id_number", "").strip(),
                    id_type=data.get("id_type", "national_id"),
                    ticket_type=ticket_type.name,
                    registration_fee=fee,
                    payment_status="free" if fee == 0 else "pending",
                    registered_by="self",
                    status="confirmed" if fee == 0 else "pending_payment",
                )

                db.session.add(registration)
                db.session.flush()
                registration.generate_refs(event.slug)
                db.session.flush()

                qr_code = cls._generate_qr_code(registration.qr_token, registration.registration_ref)
                db.session.commit()

                logger.info(f"Registration: {registration.registration_ref} for {event.slug}")

                result = cls._registration_to_dict(registration)

                # Cross-selling — use plain values, not the lazy-loaded user object
                from app.identity.models.user import User
                user = User.query.get(user_id)
                if user:
                    result['suggested_services'] = CrossSellingService.analyze_attendee_needs(
                        getattr(user, 'city', None),
                        getattr(user, 'country', None),
                        event,
                    )

                return result, qr_code, None

            except SoldOutException as e:
                raise
            except Exception as e:
                logger.warning(f"Registration attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    return None, None, "Registration failed. Please try again."

        return None, None, "Registration failed"

    @classmethod
    def register_for_event_with_payment(
        cls, identifier: str, user_id: int, data: Dict
    ) -> Tuple[Optional[Dict], Optional[str], Optional[str]]:
        """Register with wallet payment."""
        try:
            with db.session.begin_nested():
                event = Event.query.with_for_update().filter_by(slug=identifier).first()
                if not event:
                    return None, None, "Event not found"

                ticket_type_id = data.get("ticket_type_id")
                if ticket_type_id:
                    ticket_type = TicketType.query.with_for_update().filter_by(
                        id=ticket_type_id, event_id=event.id
                    ).first()
                else:
                    ticket_type = TicketType.query.with_for_update().filter_by(
                        event_id=event.id, price=0, is_active=True
                    ).first()
                if not ticket_type:
                    return None, None, "No ticket type available"

                if ticket_type.capacity > 0:
                    current = db.session.query(
                        func.count(EventRegistration.id)
                    ).filter_by(ticket_type_id=ticket_type.id).scalar()
                    if current >= ticket_type.capacity:
                        return None, None, f"'{ticket_type.name}' is sold out"

                if event.max_capacity > 0:
                    current = db.session.query(
                        func.count(EventRegistration.id)
                    ).filter_by(event_id=event.id).scalar()
                    if current >= event.max_capacity:
                        return None, None, "Event at full capacity"

                if EventRegistration.query.filter_by(event_id=event.id, user_id=user_id).first():
                    return None, None, "Already registered"

                fee = float(ticket_type.price)
                payment_txn_id = None
                payment_status = "free"

                if fee > 0:
                    if not MODULES_AVAILABLE['wallet']:
                        return None, None, "Payment service unavailable"
                    try:
                        ref = (
                            f"EVT-REG-{identifier}-{user_id}-"
                            f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                        )
                        if hasattr(WalletService, 'debit'):
                            success, result, error = WalletService.debit(
                                user_id=user_id, amount=Decimal(str(fee)),
                                currency=event.currency, reference=ref,
                                description=f"Registration: {event.name}",
                                metadata={"event_slug": identifier},
                            )
                        else:
                            ws = WalletService()
                            success, result, error = ws.debit(
                                user_id=user_id, amount=Decimal(str(fee)),
                                currency=event.currency, reference=ref,
                                description=f"Registration: {event.name}",
                                metadata={"event_slug": identifier},
                            )
                        if not success:
                            return None, None, f"Payment failed: {error}"
                        payment_txn_id = result.get("transaction_id") if result else None
                        payment_status = "paid"
                    except Exception as pe:
                        logger.error(f"Payment error: {pe}")
                        return None, None, "Payment processing failed"

                registration = EventRegistration(
                    event_id=event.id, user_id=user_id,
                    ticket_type_id=ticket_type.id,
                    full_name=data.get("full_name", "").strip(),
                    email=data.get("email", "").strip().lower(),
                    phone=data.get("phone", "").strip(),
                    nationality=data.get("nationality", "").strip(),
                    id_number=data.get("id_number", "").strip(),
                    id_type=data.get("id_type", "national_id"),
                    ticket_type=ticket_type.name,
                    registration_fee=fee,
                    payment_status=payment_status,
                    wallet_txn_id=payment_txn_id,
                    registered_by="self",
                    status="confirmed" if payment_status in ("paid", "free") else "pending_payment",
                )
                db.session.add(registration)
                db.session.flush()
                registration.generate_refs(event.slug)
                db.session.flush()

                qr_code = cls._generate_qr_code(registration.qr_token, registration.registration_ref)
                db.session.commit()
                logger.info(f"Paid registration: {registration.registration_ref}")
                return cls._registration_to_dict(registration), qr_code, None

        except Exception as e:
            logger.error(f"Paid registration failed: {e}", exc_info=True)
            return None, None, "Registration failed"

    @classmethod
    def cancel_registration(
        cls, registration_ref: str, user_id: int
    ) -> Tuple[bool, Optional[str]]:
        registration = EventRegistration.query.filter_by(
            registration_ref=registration_ref
        ).first()
        if not registration:
            return False, "Registration not found"
        if registration.user_id != user_id:
            return False, "Unauthorized"
        if registration.status in ("cancelled", "checked_in"):
            return False, f"Cannot cancel — status is '{registration.status}'"

        event = Event.query.get(registration.event_id)
        if event and event.start_date and event.start_date < date.today():
            return False, "Cannot cancel past events"

        registration.status = "cancelled"
        if registration.ticket_type_id:
            ticket_type = TicketType.query.get(registration.ticket_type_id)
            if ticket_type and ticket_type.capacity and ticket_type.capacity > 0:
                ticket_type.release_seat()

        db.session.commit()
        logger.info(f"Registration {registration_ref} cancelled")
        return True, None

    @classmethod
    def get_registration_count(cls, event_slug: str, ticket_type_id: int = None) -> int:
        event = cls.get_event_model(event_slug)
        if not event:
            return 0
        query = EventRegistration.query.filter_by(event_id=event.id)
        if ticket_type_id:
            query = query.filter_by(ticket_type_id=ticket_type_id)
        return query.count()

    @classmethod
    def get_registrations_by_event(cls, event_slug: str, status: str = None) -> List[Dict]:
        event = cls.get_event_model(event_slug)
        if not event:
            return []
        query = EventRegistration.query.options(
            joinedload(EventRegistration.event)
        ).filter_by(event_id=event.id)
        if status:
            query = query.filter_by(status=status)
        return [cls._registration_to_dict(r) for r in
                query.order_by(EventRegistration.created_at.desc()).all()]

    @classmethod
    def get_user_registrations(cls, user_id: int) -> List[Dict]:
        registrations = EventRegistration.query.options(
            joinedload(EventRegistration.event)
        ).filter_by(user_id=user_id).order_by(EventRegistration.created_at.desc()).all()
        return [cls._registration_to_dict(r) for r in registrations]

    # ========================================================================
    # CHECK-IN
    # ========================================================================

    @classmethod
    def check_in_attendee(
        cls, qr_token: str, checked_by_user_id: int
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        import hmac
        import os

        parts = qr_token.rsplit(':', 1)
        if len(parts) != 2:
            return False, "Invalid QR code", None
        payload, provided_sig = parts[0], parts[1]

        key = os.environ.get('QR_SECRET_KEY', 'dev-secret-change-in-production').encode()
        expected_sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(provided_sig, expected_sig):
            return False, "Tampered QR code", None

        payload_parts = payload.split(':')
        if len(payload_parts) < 2:
            return False, "Invalid QR format", None

        registration = EventRegistration.query.options(
            joinedload(EventRegistration.event)
        ).filter_by(registration_ref=payload_parts[1]).first()
        if not registration:
            return False, "Invalid QR code", None

        event = registration.event
        if event and event.end_date:
            if date.today() > event.end_date + timedelta(days=1):
                return False, "Ticket expired", None

        if registration.status == "checked_in":
            return False, f"Already checked in at {registration.checked_in_at.strftime('%Y-%m-%d %H:%M')}", None
        if registration.status == "cancelled":
            return False, "Registration cancelled", None

        registration.status = "checked_in"
        registration.checked_in_at = datetime.utcnow()
        registration.checked_in_by_id = checked_by_user_id
        db.session.commit()

        result = {
            "name": registration.full_name,
            "ticket_type": registration.ticket_type,
            "event_name": event.name if event else "Unknown",
            "event_venue": event.venue if event else None,
            "registration_ref": registration.registration_ref,
            "nationality": registration.nationality,
            "phone": registration.phone,
            "checked_in_at": registration.checked_in_at.isoformat(),
        }
        logger.info(f"Checked in: {registration.registration_ref}")
        return True, f"Welcome {registration.full_name}!", result

    # ========================================================================
    # WAITLIST
    # ========================================================================

    @classmethod
    @with_transaction(isolation_level="REPEATABLE_READ")
    def add_to_waitlist(
        cls, identifier: str, user_id: int, data: Dict
    ) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            event = Event.query.filter_by(slug=identifier, is_deleted=False).first()
            if not event:
                return None, "Event not found"
            if EventRegistration.query.filter_by(event_id=event.id, user_id=user_id).first():
                return None, "Already registered"
            existing = Waitlist.query.filter_by(
                event_id=event.id, user_id=user_id, status="pending"
            ).first()
            if existing:
                return cls._waitlist_to_dict(existing), "Already on waitlist"

            last_pos = db.session.query(func.max(Waitlist.position)).filter_by(
                event_id=event.id, status="pending"
            ).scalar() or 0

            entry = Waitlist(
                event_id=event.id, user_id=user_id,
                ticket_type_id=data.get("ticket_type_id"),
                position=last_pos + 1,
                email=data.get("email", ""),
                phone=data.get("phone", ""),
                status="pending",
            )
            db.session.add(entry)
            db.session.flush()
            return cls._waitlist_to_dict(entry), None
        except Exception as e:
            logger.error(f"Waitlist error: {e}")
            return None, str(e)

    # ========================================================================
    # DISCOUNT CODES
    # ========================================================================

    @classmethod
    def validate_discount_code(
        cls, identifier: str, code: str, ticket_type_id: Optional[int] = None
    ) -> Tuple[Optional[Decimal], Optional[str]]:
        from app.events.models import DiscountCode

        event = cls.get_event_model(identifier)
        if not event:
            return None, "Event not found"

        ticket_type = None
        if ticket_type_id:
            ticket_type = TicketType.query.filter_by(
                id=ticket_type_id, event_id=event.id
            ).first()
            if not ticket_type:
                return None, "Invalid ticket type"

        discount = DiscountCode.query.filter_by(
            event_id=event.id, code=code.strip().upper(), is_active=True
        ).first()
        if not discount:
            return None, "Invalid discount code"
        if not discount.is_valid():
            return None, "Discount code expired or limit reached"

        price = Decimal(str(ticket_type.price)) if ticket_type else Decimal("0.00")
        amount = discount.calculate_discount(price)
        discount.used_count = (discount.used_count or 0) + 1
        db.session.add(discount)
        return amount, None

    # ========================================================================
    # SERVICE ASSIGNMENT
    # ========================================================================

    @classmethod
    def assign_service_to_attendee(
        cls,
        attendee_id: int,
        identifier: str,
        booking_type: str,
        booking_id: int,
        managed_by: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            event = Event.query.filter_by(slug=identifier).first()
            if not event:
                return None, "Event not found"

            assignment = EventAssignment.query.filter_by(
                event_id=event.id, attendee_id=attendee_id
            ).first()
            if not assignment:
                assignment = EventAssignment(
                    event_id=event.id, attendee_id=attendee_id,
                    managed_by=managed_by, notes=notes,
                )
                db.session.add(assignment)
                db.session.flush()

            if booking_type == 'accommodation':
                assignment.accommodation_booking_id = booking_id
                if MODULES_AVAILABLE['accommodation'] and AccommodationBooking:
                    acc = AccommodationBooking.query.get(booking_id)
                    if acc:
                        acc.event_id = event.id
                        acc.event_participation_id = assignment.id
            elif booking_type == 'transport':
                assignment.transport_booking_id = booking_id
                if MODULES_AVAILABLE['transport'] and TransportBooking:
                    tp = TransportBooking.query.get(booking_id)
                    if tp:
                        tp.event_id = event.id
                        tp.event_participation_id = assignment.id
            elif booking_type == 'meal':
                assignment.meal_booking_id = booking_id
            else:
                return None, f"Invalid booking type: {booking_type}"

            db.session.commit()

            if MODULES_AVAILABLE['audit']:
                try:
                    AuditService.data_change(
                        entity_type="event_assignment",
                        entity_id=str(assignment.id),
                        operation="update", old_value=None,
                        new_value={
                            "event_id": event.id, "attendee_id": attendee_id,
                            f"{booking_type}_booking_id": booking_id,
                            "managed_by": managed_by,
                        },
                        changed_by=managed_by or attendee_id,
                        extra_data={"event_slug": identifier, "booking_type": booking_type},
                    )
                except Exception:
                    pass

            return cls._assignment_to_dict(assignment), None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Assignment error: {e}")
            return None, str(e)

    @classmethod
    def get_event_assignments(cls, identifier: str) -> List[Dict]:
        try:
            event = Event.query.filter_by(slug=identifier).first()
            if not event:
                return []
            return [
                cls._assignment_to_dict(a)
                for a in EventAssignment.query.filter_by(event_id=event.id)
                .order_by(EventAssignment.created_at.desc()).all()
            ]
        except Exception as e:
            logger.error(f"Get assignments error: {e}")
            return []

    @classmethod
    def get_attendee_assignments(cls, user_id: int) -> List[Dict]:
        try:
            return [
                cls._assignment_to_dict(a)
                for a in EventAssignment.query.filter_by(attendee_id=user_id)
                .order_by(EventAssignment.created_at.desc()).all()
            ]
        except Exception as e:
            logger.error(f"Get attendee assignments error: {e}")
            return []

    # ========================================================================
    # STATS — SQL aggregation, no Python row iteration
    # ========================================================================

    @classmethod
    def get_event_stats(cls, event_slug: str) -> Dict:
        """Single aggregation query — no row fetching."""
        event = cls.get_event_model(event_slug)
        if not event:
            return {}

        row = db.session.query(
            func.count(EventRegistration.id).label("total"),
            func.coalesce(
                func.sum(
                    case(
                        (EventRegistration.payment_status == 'paid',
                         EventRegistration.registration_fee),
                        else_=0,
                    )
                ), 0
            ).label("revenue"),
            func.count(
                case((EventRegistration.status == 'checked_in', 1))
            ).label("checked_in"),
        ).filter(EventRegistration.event_id == event.id).one()

        return {
            "event": cls._event_to_dict(event),
            "total_registrations": row.total,
            "total_revenue": float(row.revenue),
            "checked_in_count": row.checked_in,
        }

    # ========================================================================
    # DASHBOARDS — one query each
    # ========================================================================

    @classmethod
    def get_attendee_dashboard_data(cls, user_id: int) -> Dict:
        """
        Single query with joinedload — no per-registration Event.query.get().
        """
        registrations = (
            EventRegistration.query
            .options(joinedload(EventRegistration.event))
            .filter_by(user_id=user_id)
            .order_by(EventRegistration.created_at.desc())
            .all()
        )

        upcoming, past = [], []
        attended, total_spent = 0, 0.0

        for reg in registrations:
            event = reg.event          # already loaded — zero extra queries
            if not event:
                continue

            reg_dict = cls._registration_to_dict(reg)   # uses reg.event, no query

            if event.end_date and event.end_date >= date.today():
                upcoming.append(reg_dict)
            else:
                past.append(reg_dict)

            if reg.status == 'checked_in':
                attended += 1
            total_spent += float(reg.registration_fee or 0)

        upcoming.sort(key=lambda x: x['event'].get('start_date') or '9999-12-31')
        past.sort(key=lambda x: x['event'].get('start_date') or '0000-01-01', reverse=True)

        return {
            "upcoming_registrations": upcoming,
            "past_registrations": past,
            "upcoming_count": len(upcoming),
            "past_count": len(past),
            "attended_count": attended,
            "total_spent": f"{total_spent:.2f}",
        }

    @classmethod
    def get_organizer_dashboard_data(cls, user_id: int) -> Dict:
        """
        Single GROUP BY query for all registration counts + revenue.
        No per-event COUNT/SUM loop.
        """
        managed = cls.get_events_managed_by_user(user_id)

        event_ids = [
            e.id for e in
            Event.query.filter_by(organizer_id=user_id, is_deleted=False)
            .with_entities(Event.id).all()
        ]

        # One aggregation query across all events
        agg_rows = db.session.query(
            EventRegistration.event_id,
            func.count(EventRegistration.id).label("reg_count"),
            func.coalesce(
                func.sum(
                    case(
                        (EventRegistration.payment_status == 'paid',
                         EventRegistration.registration_fee),
                        else_=0,
                    )
                ), 0
            ).label("revenue"),
        ).filter(
            EventRegistration.event_id.in_(event_ids)
        ).group_by(EventRegistration.event_id).all()

        agg = {row.event_id: row for row in agg_rows}

        total_regs = sum(r.reg_count for r in agg.values())
        total_rev = sum(float(r.revenue) for r in agg.values())

        # Active events with injected counts
        active_events = []
        for event in Event.query.filter(
            Event.id.in_(event_ids),
            Event.status.in_([EventStatus.PUBLISHED.value, EventStatus.ACTIVE.value]),
        ).all():
            row = agg.get(event.id)
            ed = cls._event_to_dict(event)
            ed['registration_count'] = row.reg_count if row else 0
            ed['revenue'] = float(row.revenue) if row else 0.0
            active_events.append(ed)

        return {
            "stats": {
                "total_events": len(managed),
                "total_registrations": total_regs,
                "total_revenue": f"{total_rev:.2f}",
                "active_events": len(active_events),
            },
            "active_events": active_events[:5],
            "managed_events": managed,
        }

    @classmethod
    def get_admin_dashboard_data(cls) -> Dict:
        """
        Single GROUP BY query replaces 9 individual COUNT queries.
        """
        try:
            # One query — group by status
            status_rows = db.session.query(
                Event.status,
                func.count(Event.id).label("cnt"),
            ).filter_by(is_deleted=False).group_by(Event.status).all()

            counts = {row.status: row.cnt for row in status_rows}

            def c(status: EventStatus) -> int:
                # counts keys may be enum members or strings depending on driver
                return counts.get(status) or counts.get(status.value) or 0

            # Registration aggregations — two counts in one query
            reg_row = db.session.query(
                func.count(EventRegistration.id).label("total"),
                func.count(
                    case((EventRegistration.status == 'checked_in', 1))
                ).label("checked_in"),
            ).one()

            return {
                'total_events':          sum(counts.values()),
                'published_events':      c(EventStatus.PUBLISHED),
                'pending_events':        c(EventStatus.PENDING_APPROVAL),
                'approved_events':       c(EventStatus.APPROVED),
                'rejected_events':       c(EventStatus.REJECTED),
                'draft_events':          c(EventStatus.DRAFT),
                'suspended_events':      c(EventStatus.SUSPENDED),
                'paused_events':         c(EventStatus.PAUSED),
                'completed_events':      c(EventStatus.COMPLETED),
                'cancelled_events':      c(EventStatus.CANCELLED),
                'archived_events':       c(EventStatus.ARCHIVED),
                'active_events':         c(EventStatus.ACTIVE),   # legacy
                'total_registrations':   reg_row.total,
                'checked_in_registrations': reg_row.checked_in,
            }
        except Exception as e:
            logger.error(f"Admin dashboard error: {e}", exc_info=True)
            return {k: 0 for k in [
                'total_events', 'published_events', 'pending_events', 'approved_events',
                'rejected_events', 'draft_events', 'suspended_events', 'paused_events',
                'completed_events', 'cancelled_events', 'archived_events', 'active_events',
                'total_registrations', 'checked_in_registrations',
            ]}

    @classmethod
    def get_service_provider_dashboard_data(cls, user_id: int) -> Dict:
        """Service provider dashboard — uses signals for loose coupling."""
        dashboard = {
            "user_properties": [], "user_vehicles": [],
            "relevant_events": [], "event_assignments": [],
            "property_count": 0, "vehicle_count": 0,
        }

        if SIGNALS_AVAILABLE:
            try:
                responses = []
                def collect(sender, **kwargs):
                    responses.append(kwargs)
                service_provider_data_requested.connect(collect, weak=False)
                service_provider_data_requested.send(
                    current_app._get_current_object(),
                    user_id=user_id, dashboard_data=dashboard,
                )
                service_provider_data_requested.disconnect(collect)
                for r in responses:
                    if 'properties' in r:
                        dashboard['user_properties'].extend(r['properties'])
                    if 'vehicles' in r:
                        dashboard['user_vehicles'].extend(r['vehicles'])
                    if 'event_assignments' in r:
                        dashboard['event_assignments'].extend(r['event_assignments'])
            except Exception as e:
                logger.warning(f"Signal collection failed: {e}")

        service_cities = set()
        for p in dashboard['user_properties']:
            city = p.get('city') if isinstance(p, dict) else getattr(p, 'city', None)
            if city:
                service_cities.add(city)
        for v in dashboard['user_vehicles']:
            loc = (v.get('current_location') if isinstance(v, dict)
                   else getattr(v, 'current_location', None))
            if loc:
                service_cities.add(loc)

        if service_cities:
            events = Event.query.filter(
                Event.status == EventStatus.PUBLISHED,
                Event.is_deleted == False,
                Event.city.in_(list(service_cities)),
            ).order_by(Event.start_date).limit(5).all()
            dashboard['relevant_events'] = [cls._event_to_dict(e) for e in events]

        dashboard['property_count'] = len(dashboard['user_properties'])
        dashboard['vehicle_count'] = len(dashboard['user_vehicles'])
        return dashboard

    # ========================================================================
    # QR CODE
    # ========================================================================

    @classmethod
    def _generate_qr_code(cls, qr_token: str, registration_ref: str) -> str:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_token)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

    # ========================================================================
    # SERIALIZATION — no DB queries inside these methods
    # ========================================================================

    @classmethod
    def _fetch_ticket_reg_counts(cls, event_ids: List[int]) -> Dict[int, int]:
        """
        Return {ticket_type_id: registration_count} for all ticket types
        belonging to the given event IDs. Single query.
        """
        if not event_ids:
            return {}
        rows = db.session.query(
            EventRegistration.ticket_type_id,
            func.count(EventRegistration.id).label("cnt"),
        ).join(
            TicketType, EventRegistration.ticket_type_id == TicketType.id
        ).filter(
            TicketType.event_id.in_(event_ids)
        ).group_by(EventRegistration.ticket_type_id).all()
        return {row.ticket_type_id: row.cnt for row in rows}

    @classmethod
    def _event_to_dict(cls, event: Event, reg_counts: Dict[int, int] = None) -> Dict:
        """
        Convert Event model to dict.
        `reg_counts` is the pre-fetched {ticket_type_id: count} map.
        If omitted (single-event calls) a targeted query is run once.
        """
        if not event:
            return {}

        if reg_counts is None:
            # Single-event call — fetch counts for just this event
            reg_counts = cls._fetch_ticket_reg_counts([event.id])

        website = event.website if event.website != "" else None

        return {
            "id": event.public_id,
            "slug": event.slug,
            "event_ref": event.event_ref,
            "name": event.name,
            "description": event.description,
            "category": event.category,
            "city": event.city,
            "country": event.country,
            "venue": event.venue,
            "start_date": event.start_date.isoformat() if event.start_date else None,
            "end_date": event.end_date.isoformat() if event.end_date else None,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "updated_at": event.updated_at.isoformat() if event.updated_at else None,
            "max_capacity": event.max_capacity,
            "registration_required": event.registration_required,
            "registration_fee": float(event.registration_fee) if event.registration_fee else 0,
            "currency": event.currency,
            "status": cls.sanitize_status(event.status),
            "featured": event.featured,
            "organizer_id": event.organizer_id,
            "website": website,
            "contact_email": event.contact_email,
            "contact_phone": event.contact_phone,
            "metadata": event.event_metadata or {},
            "approved_at": event.approved_at.isoformat() if event.approved_at else None,
            "rejected_at": event.rejected_at.isoformat() if event.rejected_at else None,
            "rejection_reason": event.rejection_reason,
            "completed_at": event.completed_at.isoformat() if event.completed_at else None,
            "deletion_reason": event.deletion_reason,
            "is_terminal": event.is_terminal,
            "accepts_registrations": event.accepts_registrations,
            # Submission preferences (new fields — safe if columns not yet migrated)
            "auto_publish_on_approval": getattr(event, 'auto_publish_on_approval', False),
            "publish_permission": getattr(event, 'publish_permission', 'either'),
            "ticket_types": [
                cls._ticket_type_to_dict(tt, reg_counts)
                for tt in (event.ticket_types or [])
            ],
        }

    @classmethod
    def _ticket_type_to_dict(cls, tt: TicketType, reg_counts: Dict[int, int] = None) -> Dict:
        """
        No DB query. reg_counts map is passed in from the caller.
        Falls back to a direct count only when called in isolation
        (e.g. add_ticket_type response).
        """
        if reg_counts is None:
            count = EventRegistration.query.filter_by(ticket_type_id=tt.id).count()
        else:
            count = reg_counts.get(tt.id, 0)

        return {
            "id": tt.id,
            "name": tt.name,
            "description": tt.description,
            "price": float(tt.price),
            "capacity": tt.capacity,
            "available_seats": tt.available_seats,
            "registration_count": count,
            "available_from": tt.available_from.isoformat() if tt.available_from else None,
            "available_until": tt.available_until.isoformat() if tt.available_until else None,
            "is_active": tt.is_active,
            "is_sold_out": tt.is_sold_out_flag,
        }

    @classmethod
    def _registration_to_dict(cls, registration) -> Dict:
        """
        Uses registration.event relationship — no extra Event.query.get().
        Callers must use joinedload(EventRegistration.event) at the query site.
        """
        event = registration.event  # ORM relationship — no query if joinedloaded

        if event:
            event_dict = {
                "id": event.public_id,
                "slug": event.slug,
                "name": event.name,
                "start_date": event.start_date.isoformat() if event.start_date else None,
                "end_date": event.end_date.isoformat() if event.end_date else None,
            }
        else:
            event_dict = {
                "id": None, "slug": None, "name": "Unknown Event",
                "start_date": None, "end_date": None,
            }

        result = {
            "id": registration.id,
            "registration_ref": registration.registration_ref,
            "ticket_number": registration.ticket_number or registration.registration_ref,
            "qr_token_hint": (registration.qr_token[:8] + '...') if registration.qr_token else None,
            "full_name": registration.full_name,
            "email": registration.email,
            "phone": registration.phone,
            "nationality": registration.nationality,
            "ticket_type": registration.ticket_type or "General Admission",
            "ticket_type_id": registration.ticket_type_id,
            "status": registration.status or "confirmed",
            "payment_status": registration.payment_status or "free",
            "registration_fee": float(registration.registration_fee or 0),
            "checked_in_at": registration.checked_in_at.isoformat() if registration.checked_in_at else None,
            "created_at": registration.created_at.isoformat() if registration.created_at else None,
            "event": event_dict,
        }

        if hasattr(registration, 'discount_code_applied'):
            result['discount_code_applied'] = registration.discount_code_applied
        if hasattr(registration, 'discount_amount'):
            result['discount_amount'] = float(registration.discount_amount or 0)

        # Assignment — only query if needed; keep as optional enrichment
        try:
            assignment = EventAssignment.query.filter_by(
                event_id=registration.event_id,
                attendee_id=registration.user_id,
            ).first()
            if assignment:
                result['assignment'] = cls._assignment_to_dict(assignment)
        except Exception as e:
            logger.warning(f"Could not load assignment: {e}")

        return result

    @classmethod
    def _waitlist_to_dict(cls, wl: Waitlist) -> Dict:
        return {
            "id": wl.id, "event_id": wl.event_id, "user_id": wl.user_id,
            "ticket_type_id": wl.ticket_type_id, "position": wl.position,
            "status": wl.status, "email": wl.email, "phone": wl.phone,
            "created_at": wl.created_at.isoformat() if wl.created_at else None,
            "notified_at": wl.notified_at.isoformat() if wl.notified_at else None,
            "converted_at": wl.converted_at.isoformat() if wl.converted_at else None,
        }

    @classmethod
    def _assignment_to_dict(cls, assignment) -> Dict:
        return {
            "id": assignment.id,
            "event_id": assignment.event_id,
            "attendee_id": assignment.attendee_id,
            "accommodation_booking_id": assignment.accommodation_booking_id,
            "transport_booking_id": assignment.transport_booking_id,
            "meal_booking_id": assignment.meal_booking_id,
            "managed_by": assignment.managed_by,
            "notes": assignment.notes,
            "schedule_json": assignment.schedule_json,
            "status": assignment.status,
            "registration_id": assignment.registration_id,
            "created_at": assignment.created_at.isoformat() if assignment.created_at else None,
            "updated_at": assignment.updated_at.isoformat() if assignment.updated_at else None,
        }