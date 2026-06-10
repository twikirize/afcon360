# app/events/services.py - OPTIMIZED VERSION (FIXED CIRCULAR IMPORT)
# Changes: Fixed N+1 queries in get_attendee_dashboard_data, removed circular import

"""
Event Service - DB-backed event management
Now using SQLAlchemy models instead of in-memory dict
"""
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Optional, Tuple, Any
import logging
import re
import qrcode
import functools
import hashlib
from io import BytesIO
import base64
import secrets
from flask import url_for, current_app
from app.extensions import db, redis_client
# REMOVED: import app.events.models  <-- THIS CAUSED CIRCULAR IMPORT
from app.admin.models import ContentFlag
from app.events.constants import EventStatus
from app.events.trust_service import EventTrustService, TrustLevel

# Remove tight coupling to accommodation module
try:
    from app.accommodation.models.booking import BookingContextType
except ImportError:
    from enum import Enum
    class BookingContextType(Enum):
        EVENT = "event"
        TOURISM = "tourism"
        TRANSPORT = "transport"
        GENERAL = "general"
from sqlalchemy import func, case, and_
from decimal import Decimal

logger = logging.getLogger(__name__)


def sanitize_status(status_value):
    """Safely convert any status value to a valid EventStatus string."""
    from app.events.constants import EventStatus

    if status_value is None:
        return EventStatus.DRAFT.value
    if isinstance(status_value, EventStatus):
        return status_value.value

    status_str = str(status_value).strip()

    if status_str.startswith("EventStatus."):
        enum_name = status_str.split(".", 1)[1]
        logger.error(f"sanitize_status received a Python enum repr '{status_str}'. Attempting recovery.")
        try:
            return EventStatus[enum_name].value
        except KeyError:
            logger.error(f"Recovery failed - unknown enum name '{enum_name}', defaulting to DRAFT")
            return EventStatus.DRAFT.value

    try:
        return EventStatus(status_str).value
    except ValueError:
        pass

    try:
        return EventStatus[status_str.upper()].value
    except KeyError:
        pass

    logger.warning(f"Legacy status value encountered: '{status_str}', defaulting to DRAFT")
    return EventStatus.DRAFT.value


# Service provider data will be fetched via signals or separate services
Property = None
Vehicle = None


def with_transaction(isolation_level="REPEATABLE_READ"):
    """Decorator to ensure methods run within a database transaction."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if db.session.is_active:
                return func(*args, **kwargs)
            original_isolation = db.session.connection().connection.isolation_level
            try:
                db.session.connection().connection.set_isolation_level(
                    getattr(db.session.connection().connection, f'ISOLATION_LEVEL_{isolation_level}')
                )
                with db.session.begin_nested():
                    result = func(*args, **kwargs)
                    return result
            except Exception as e:
                db.session.rollback()
                logger.error(f"Transaction failed in {func.__name__}: {e}")
                raise
            finally:
                db.session.connection().connection.set_isolation_level(original_isolation)
        return wrapper
    return decorator


class IdempotencyChecker:
    """Prevents duplicate processing of requests."""
    @staticmethod
    def check_and_store(key: str, ttl_seconds: int = 300) -> bool:
        if not redis_client:
            return False
        cache_key = f"idempotency:{key}"
        result = redis_client.set(cache_key, "1", nx=True, ex=ttl_seconds)
        return result is not True

    @staticmethod
    def generate_key(user_id: int, identifier: str, data_hash: str) -> str:
        key_data = f"{user_id}:{identifier}:{data_hash}"
        return hashlib.sha256(key_data.encode()).hexdigest()


try:
    from app.wallet.services.wallet_service import WalletService
except ImportError as e:
    logger.warning(f"WalletService not found: {e}")
    WalletService = None

try:
    from app.events.signal_handlers import (
        event_registered, event_cancelled, event_capacity_released,
        offer_services_after_registration, service_provider_data_requested
    )
    SIGNALS_AVAILABLE = True
except ImportError:
    SIGNALS_AVAILABLE = False
    logger.warning("Signals not available")


def _assert_no_open_flags(event_id: int):
    count = ContentFlag.query.filter_by(
        entity_type="event", entity_id=event_id, status="open"
    ).count()
    if count:
        raise ValueError(f"Cannot publish event {event_id}: {count} open moderation flag(s) must be resolved first.")


class SoldOutException(Exception):
    pass


class EventService:
    """Event management with database persistence"""

    # Helper to import models only when needed (avoids circular import)
    @staticmethod
    def _get_event_model_class():
        from app.events.models import Event
        return Event

    @staticmethod
    def _get_ticket_type_class():
        from app.events.models import TicketType
        return TicketType

    @staticmethod
    def _get_registration_class():
        from app.events.models import EventRegistration
        return EventRegistration

    @staticmethod
    def _get_waitlist_class():
        from app.events.models import Waitlist
        return Waitlist

    @staticmethod
    def _get_assignment_class():
        from app.events.models import EventAssignment
        return EventAssignment

    @classmethod
    def get_all_events(cls, status: str = None) -> List[Dict]:
        Event = cls._get_event_model_class()
        query = Event.query
        if status:
            sanitized_status = cls.sanitize_status(status)
            query = query.filter_by(status=sanitized_status)
        else:
            query = query.filter_by(status=EventStatus.PUBLISHED)
        events = query.order_by(Event.start_date).all()
        return [cls._event_to_dict(event) for event in events]

    @classmethod
    def get_event(cls, event_id: str) -> Optional[Dict]:
        Event = cls._get_event_model_class()
        event = Event.query.filter_by(slug=event_id).first()
        return cls._event_to_dict(event) if event else None

    @classmethod
    def change_event_status(cls, event_id: str, new_status: str, user_id: int,
                            reason: str = None, ip_address: str = None,
                            user_agent: str = None) -> Tuple[bool, Optional[str]]:
        from app.events.constants import EventStatus
        from app.events.models import EventModerationLog
        from app.identity.models.user import User as UserModel
        from app.auth.helpers import has_global_permission

        event = cls.get_event_model(event_id)
        if not event:
            return False, "Event not found"

        if isinstance(new_status, str):
            try:
                new_status = EventStatus(new_status)
            except ValueError:
                return False, f"Invalid status: {new_status}"

        ALLOWED_TRANSITIONS = {
            EventStatus.PENDING_APPROVAL: [EventStatus.APPROVED, EventStatus.REJECTED],
            EventStatus.APPROVED: [EventStatus.PUBLISHED],
            EventStatus.PUBLISHED: [EventStatus.SUSPENDED, EventStatus.PAUSED, EventStatus.CANCELLED],
            EventStatus.SUSPENDED: [EventStatus.PUBLISHED],
            EventStatus.PAUSED: [EventStatus.PUBLISHED],
            EventStatus.CANCELLED: [EventStatus.ARCHIVED],
            EventStatus.REJECTED: [EventStatus.DELETED],
            EventStatus.DRAFT: [EventStatus.PENDING_APPROVAL, EventStatus.DELETED],
            EventStatus.ARCHIVED: [EventStatus.DELETED],
        }

        if event.status not in ALLOWED_TRANSITIONS:
            return False, f"Cannot transition from status {event.status.value}"
        if new_status not in ALLOWED_TRANSITIONS[event.status]:
            return False, f"Cannot transition from {event.status.value} to {new_status.value}"

        ACTION_MAP = {
            (EventStatus.PENDING_APPROVAL, EventStatus.APPROVED): 'approve',
            (EventStatus.PENDING_APPROVAL, EventStatus.REJECTED): 'reject',
            (EventStatus.PUBLISHED, EventStatus.SUSPENDED): 'suspend',
            (EventStatus.SUSPENDED, EventStatus.PUBLISHED): 'reactivate',
            (EventStatus.PUBLISHED, EventStatus.PAUSED): 'pause',
            (EventStatus.PAUSED, EventStatus.PUBLISHED): 'resume',
            (EventStatus.DRAFT, EventStatus.DELETED): 'delete',
            (EventStatus.REJECTED, EventStatus.DELETED): 'delete',
            (EventStatus.ARCHIVED, EventStatus.DELETED): 'delete',
            (EventStatus.APPROVED, EventStatus.PUBLISHED): 'publish',
            (EventStatus.PUBLISHED, EventStatus.CANCELLED): 'cancel',
            (EventStatus.CANCELLED, EventStatus.ARCHIVED): 'archive',
        }

        action = ACTION_MAP.get((event.status, new_status), 'status_change')

        user = UserModel.query.get(user_id)
        if not user:
            return False, "User not found"

        if new_status in (EventStatus.APPROVED, EventStatus.REJECTED):
            if not has_global_permission(user, "events.approve"):
                return False, "You do not have permission to approve or reject events"
        elif new_status in (EventStatus.SUSPENDED, EventStatus.DELETED):
            if not has_global_permission(user, "content.moderate"):
                return False, "You do not have permission to suspend or delete events"
        elif new_status == EventStatus.PUBLISHED:
            is_organizer = (event.organizer_id == user_id)
            if not (has_global_permission(user, "events.approve") or is_organizer):
                return False, "You do not have permission to publish this event"

        if new_status == EventStatus.PUBLISHED:
            _assert_no_open_flags(event.id)

        if (event.status == EventStatus.APPROVED and new_status == EventStatus.APPROVED and
            event.event_metadata and event.event_metadata.get("auto_publish_on_approval")):
            new_status = EventStatus.PUBLISHED
            action = 'publish'
            logger.info(f"Auto-publishing event {event.id} for medium-trust user after approval")

        old_status = event.status
        event.status = new_status

        if new_status == EventStatus.APPROVED:
            event.approved_at = datetime.now(timezone.utc)
            event.approved_by_id = user_id
        elif new_status == EventStatus.REJECTED:
            event.rejected_at = datetime.now(timezone.utc)
            event.rejection_reason = reason

        log_entry = EventModerationLog(
            event_id=event.id, user_id=user_id, action=action,
            from_status=old_status, to_status=new_status, reason=reason,
            ip_address=ip_address, user_agent=user_agent
        )
        db.session.add(log_entry)

        try:
            db.session.commit()
            logger.info(f"Event {event.slug} status changed from {old_status.value} to {new_status.value} by user {user_id}")
            return True, None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to change event status: {e}")
            return False, str(e)

    @classmethod
    def create_event(cls, data: Dict, user_id: int, creator_type: str = 'individual', organization_id: int = None) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            from app.auth.helpers import has_global_role, has_org_role
            from app.identity.models.user import User
            from app.events.models import Event, TicketType, EventStatus

            user = User.query.get(user_id)
            if not user:
                return None, 'User not found'

            can_create_system = has_global_role(user, 'owner', 'super_admin', 'admin', 'event_manager')

            if creator_type == 'system' and not can_create_system:
                return None, 'Only system admins can create system events'

            if creator_type == 'organization':
                if not organization_id:
                    return None, 'Organization ID required'
                if not has_org_role(user, organization_id, 'org_owner', 'org_admin'):
                    return None, 'Not authorized to create events for this organization'

            slug = re.sub(r"[^a-z0-9]+", "-", data["name"].lower()).strip("-")
            original_slug = slug
            counter = 1
            while Event.query.filter_by(slug=slug).first():
                slug = f"{original_slug}-{counter}"
                counter += 1

            if creator_type == 'organization':
                organizer_id = organization_id
            else:
                organizer_id = user_id

            from app.events.settings_model import EventSettings
            evt_settings = EventSettings.get()

            status = EventStatus.PENDING_APPROVAL
            approved_at = None
            approved_by_id = None

            trust_level = EventTrustService.calculate_trust_level(user)
            should_auto_publish, trust_reason = EventTrustService.should_auto_publish(user, trust_level)
            logger.info(f"Trust analysis for user {user.id}: Level={trust_level}, Auto-publish={should_auto_publish}")

            if evt_settings.auto_publish:
                status = EventStatus.PUBLISHED
                approved_at = datetime.now(timezone.utc)
                approved_by_id = user_id
            elif trust_level == TrustLevel.HIGH:
                status = EventStatus.PUBLISHED
                approved_at = datetime.now(timezone.utc)
                approved_by_id = user_id
                logger.info(f"High trust user {user.username} - event auto-published")
            elif trust_level == TrustLevel.MEDIUM:
                status = EventStatus.APPROVED
                approved_at = datetime.now(timezone.utc)
                approved_by_id = user_id
                event_metadata = data.get("metadata", {})
                event_metadata["auto_publish_on_approval"] = True
                data["metadata"] = event_metadata
                logger.info(f"Medium trust user {user.username} - event auto-approved for publishing")
            elif evt_settings.event_manager_auto_approve and has_global_role(user, 'event_manager'):
                status = EventStatus.APPROVED
                approved_at = datetime.now(timezone.utc)
                approved_by_id = user_id
            elif not evt_settings.require_approval:
                status = EventStatus.APPROVED
                approved_at = datetime.now(timezone.utc)
                approved_by_id = user_id

            event = Event(
                slug=slug, name=data["name"], description=data.get("description", ""),
                category=data.get("category", "other"), city=data["city"], country=data.get("country", "Uganda"),
                venue=data.get("venue", ""),
                start_date=datetime.strptime(data["start_date"], "%Y-%m-%d").date() if data.get("start_date") else None,
                end_date=datetime.strptime(data["end_date"], "%Y-%m-%d").date() if data.get("end_date") else None,
                registration_required=data.get("registration_required", False),
                currency=data.get("currency", "USD"), organizer_id=organizer_id,
                website=data.get("website"), contact_email=data.get("contact_email"),
                contact_phone=data.get("contact_phone"), event_metadata=data.get("metadata", {}),
                status=status, created_by_type=creator_type,
                organization_id=organization_id if creator_type == 'organization' else None,
                is_system_event=(creator_type == 'system'), original_creator_id=user_id,
                current_owner_type=creator_type,
                current_owner_id=organization_id if creator_type == 'organization' else user_id,
                approved_at=approved_at, approved_by_id=approved_by_id,
            )

            event.generate_ref()
            db.session.add(event)
            db.session.flush()

            if status == EventStatus.PUBLISHED:
                _assert_no_open_flags(event.id)

            if data.get("registration_required"):
                event_type = data.get("event_type", "free")
                if event_type == "free":
                    ticket = TicketType(event_id=event.id, name="Free Entry", description="Free admission", price=0, capacity=0, is_active=True)
                    db.session.add(ticket)
                elif event_type in ("paid", "ticketed"):
                    if not data.get("ticket_tiers"):
                        db.session.rollback()
                        return None, "Paid events require at least one ticket tier."
                    for tier_data in data["ticket_tiers"]:
                        available_from = None
                        available_until = None
                        if tier_data.get("available_from"):
                            try:
                                available_from = datetime.fromisoformat(tier_data["available_from"].replace('Z', '+00:00'))
                            except (ValueError, AttributeError):
                                pass
                        if tier_data.get("available_until"):
                            try:
                                available_until = datetime.fromisoformat(tier_data["available_until"].replace('Z', '+00:00'))
                            except (ValueError, AttributeError):
                                pass
                        ticket = TicketType(event_id=event.id, name=tier_data["name"], price=tier_data["price"],
                                          capacity=tier_data.get("capacity", 0), is_active=True,
                                          available_from=available_from, available_until=available_until)
                        db.session.add(ticket)
                else:
                    db.session.rollback()
                    return None, f"Invalid event type: {event_type}. Must be 'free' or 'paid'."

            db.session.commit()

            try:
                if status == EventStatus.PENDING_APPROVAL:
                    from app.admin.moderator.pipeline import submit_for_moderation
                    submit_for_moderation(entity_type="event", object_id=event.id,
                                        reason="New event submission - awaiting moderator review",
                                        submitted_by_user=user, priority="normal")
            except Exception as mod_exc:
                logger.warning(f"Moderation submit failed for event {event.id}: {mod_exc}")

            logger.info(f"Event created: {event.slug} by user {user_id}")
            return cls._event_to_dict(event), None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating event: {e}")
            return None, str(e)

    @classmethod
    def update_event(cls, event_id: str, data: Dict, user_id: int) -> Tuple[bool, Optional[str]]:
        Event = cls._get_event_model_class()
        event = Event.query.filter_by(slug=event_id).first()
        if not event:
            return False, "Event not found"
        if event.organizer_id != user_id:
            return False, "Unauthorized"
        try:
            for key, value in data.items():
                if key == "name":
                    event.name = value
                elif key == "description":
                    event.description = value
                elif key == "city":
                    event.city = value
                elif key == "venue":
                    event.venue = value
                elif key == "start_date" and value:
                    event.start_date = datetime.strptime(value, "%Y-%m-%d").date()
                elif key == "end_date" and value:
                    event.end_date = datetime.strptime(value, "%Y-%m-%d").date()
                elif key == "website":
                    event.website = value
                elif key == "contact_email":
                    event.contact_email = value
                elif key == "contact_phone":
                    event.contact_phone = value
            event.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            return False, str(e)

    @classmethod
    def delete_event(cls, event_id: str, user_id: int) -> Tuple[bool, Optional[str]]:
        Event = cls._get_event_model_class()
        Registration = cls._get_registration_class()
        event = Event.query.filter_by(slug=event_id).first()
        if not event:
            return False, "Event not found"
        if event.organizer_id != user_id:
            return False, "Unauthorized"
        registrations = Registration.query.filter_by(event_id=event.id).count()
        if registrations > 0:
            return False, f"Cannot delete event with {registrations} existing registrations"
        from sqlalchemy import func
        event.is_deleted = True
        event.deleted_at = func.now()
        event.deleted_by_id = user_id
        event.status = EventStatus.ARCHIVED
        db.session.commit()
        return True, None

    @classmethod
    def get_events_by_organizer(cls, organizer_id: int) -> List[Dict]:
        Event = cls._get_event_model_class()
        events = Event.query.filter_by(organizer_id=organizer_id).order_by(Event.created_at.desc()).all()
        return [cls._event_to_dict(event) for event in events]

    @classmethod
    def get_featured_event(cls) -> Optional[Dict]:
        Event = cls._get_event_model_class()
        featured = Event.query.filter_by(featured=True, status=EventStatus.PUBLISHED).first()
        if featured:
            return cls._event_to_dict(featured)
        from datetime import date
        upcoming = Event.query.filter(Event.status == EventStatus.PUBLISHED, Event.start_date >= date.today()
        ).order_by(Event.start_date).first()
        return cls._event_to_dict(upcoming) if upcoming else None

    @classmethod
    def get_upcoming_events(cls, limit: int = 3, exclude_featured: bool = False) -> List[Dict]:
        from datetime import date
        Event = cls._get_event_model_class()
        query = Event.query.filter(Event.status == EventStatus.PUBLISHED, Event.start_date >= date.today()
        ).order_by(Event.start_date)
        events = query.limit(limit + 1).all()
        if exclude_featured:
            featured = cls.get_featured_event()
            if featured:
                events = [e for e in events if e.slug != featured.get('slug')]
        return [cls._event_to_dict(event) for event in events[:limit]]

    @classmethod
    def get_event_stats(cls, event_id: str) -> Dict:
        event = cls.get_event_model(event_id)
        if not event:
            return {}
        Registration = cls._get_registration_class()
        registrations = Registration.query.filter_by(event_id=event.id).all()
        total_registrations = len(registrations)
        total_revenue = sum(float(r.registration_fee) for r in registrations if r.payment_status == 'paid')
        checked_in_count = len([r for r in registrations if r.status == 'checked_in'])
        return {"event": cls._event_to_dict(event), "total_registrations": total_registrations,
                "total_revenue": total_revenue, "checked_in_count": checked_in_count}

    @classmethod
    def get_event_model(cls, event_id: str):
        """Get the actual Event model instance"""
        Event = cls._get_event_model_class()
        return Event.query.filter_by(slug=event_id).first()

    @classmethod
    def approve_event(cls, event_id: str, admin_id: int) -> Tuple[bool, Optional[str]]:
        event = cls.get_event_model(event_id)
        if not event:
            return False, "Event not found"
        _assert_no_open_flags(event.id)
        event.status = EventStatus.PUBLISHED
        event.approved_at = datetime.now(timezone.utc)
        event.approved_by_id = admin_id
        event.rejected_at = None
        event.rejection_reason = None
        db.session.commit()
        logger.info(f"Event approved: {event.slug} by admin {admin_id}")
        return True, None

    @classmethod
    def reject_event(cls, event_id: str, admin_id: int, reason: str = None) -> Tuple[bool, Optional[str]]:
        event = cls.get_event_model(event_id)
        if not event:
            return False, "Event not found"
        event.status = EventStatus.REJECTED
        event.rejected_at = datetime.now(timezone.utc)
        event.rejection_reason = reason
        event.approved_at = None
        event.approved_by_id = None
        db.session.commit()
        logger.info(f"Event rejected: {event.slug} by admin {admin_id}")
        return True, None

    @classmethod
    def _event_to_dict(cls, event) -> Dict:
        website = event.website
        if website == "":
            website = None
        status_value = event.status if event.status else None
        sanitized_status = cls.sanitize_status(status_value) if status_value else None
        return {
            "id": event.public_id, "slug": event.slug, "event_ref": event.event_ref,
            "name": event.name, "description": event.description, "category": event.category,
            "city": event.city, "country": event.country, "venue": event.venue,
            "start_date": event.start_date.isoformat() if event.start_date else None,
            "end_date": event.end_date.isoformat() if event.end_date else None,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "updated_at": event.updated_at.isoformat() if event.updated_at else None,
            "max_capacity": event.max_capacity, "registration_required": event.registration_required,
            "registration_fee": float(event.registration_fee) if event.registration_fee else 0,
            "currency": event.currency, "status": sanitized_status, "featured": event.featured,
            "organizer_id": event.organizer_id, "website": website,
            "contact_email": event.contact_email, "contact_phone": event.contact_phone,
            "metadata": event.event_metadata or {},
            "approved_at": event.approved_at.isoformat() if event.approved_at else None,
            "rejected_at": event.rejected_at.isoformat() if event.rejected_at else None,
            "rejection_reason": event.rejection_reason,
            "ticket_types": [cls._ticket_type_to_dict(tt) for tt in event.ticket_types] if event.ticket_types else []
        }

    @classmethod
    def _ticket_type_to_dict(cls, ticket_type) -> Dict:
        Registration = cls._get_registration_class()
        reg_count = Registration.query.filter_by(ticket_type_id=ticket_type.id).count()
        metadata = {}
        if ticket_type.event and ticket_type.event.event_metadata:
            metadata = ticket_type.event.event_metadata.get(f"ticket_tier_{ticket_type.id}", {})
        return {
            "id": ticket_type.id, "name": ticket_type.name,
            "description": metadata.get("description", ticket_type.description or ""),
            "price": float(ticket_type.price), "capacity": ticket_type.capacity,
            "registration_count": reg_count,
            "available_from": ticket_type.available_from.isoformat() if ticket_type.available_from else None,
            "available_until": ticket_type.available_until.isoformat() if ticket_type.available_until else None,
            "is_active": ticket_type.is_active, "benefits": metadata.get("benefits", []),
            "min_purchase": metadata.get("min_purchase", 1), "payment_methods": metadata.get("payment_methods", [])
        }

    @classmethod
    def get_registration_count(cls, event_id: str, ticket_type_id: int = None) -> int:
        event = cls.get_event_model(event_id)
        if not event:
            return 0
        Registration = cls._get_registration_class()
        query = Registration.query.filter_by(event_id=event.id)
        if ticket_type_id:
            query = query.filter_by(ticket_type_id=ticket_type_id)
        return query.count()

    @classmethod
    def get_registrations_by_event(cls, event_id: str, status: str = None) -> List[Dict]:
        event = cls.get_event_model(event_id)
        if not event:
            return []
        Registration = cls._get_registration_class()
        query = Registration.query.filter_by(event_id=event.id)
        if status:
            query = query.filter_by(status=status)
        registrations = query.order_by(Registration.created_at.desc()).all()
        return [cls._registration_to_dict(reg) for reg in registrations]

    @classmethod
    def get_user_registrations(cls, user_id: int) -> List[Dict]:
        Registration = cls._get_registration_class()
        registrations = Registration.query.filter_by(user_id=user_id).order_by(Registration.created_at.desc()).all()
        return [cls._registration_to_dict(reg) for reg in registrations]

    @classmethod
    @with_transaction(isolation_level="REPEATABLE_READ")
    def register_for_event_optimistic(cls, identifier: str, user_id: int, data: Dict,
                                      idempotency_key: str = None, max_retries: int = 3) -> Tuple[
        Optional[Dict], Optional[str], Optional[str]]:
        from sqlalchemy import func, and_
        from decimal import Decimal

        if idempotency_key:
            if IdempotencyChecker.check_and_store(idempotency_key):
                logger.warning(f"Duplicate registration attempt detected: {idempotency_key}")
                Event = cls._get_event_model_class()
                Registration = cls._get_registration_class()
                event = Event.query.filter_by(slug=identifier).first()
                if event:
                    existing_reg = Registration.query.filter_by(event_id=event.id, user_id=user_id).first()
                else:
                    existing_reg = None
                if existing_reg:
                    qr_code = cls._generate_qr_code(existing_reg.qr_token, existing_reg.registration_ref)
                    return cls._registration_to_dict(existing_reg), qr_code, "Duplicate request - registration already processed"
                return None, None, "Duplicate request"

        if not idempotency_key:
            data_hash = hashlib.sha256(str(sorted(data.items())).encode()).hexdigest()
            idempotency_key = IdempotencyChecker.generate_key(user_id, identifier, data_hash)

        for attempt in range(max_retries):
            try:
                Event = cls._get_event_model_class()
                TicketType = cls._get_ticket_type_class()
                Registration = cls._get_registration_class()

                event = Event.query.filter_by(slug=identifier).first()
                if not event:
                    return None, None, "Event not found"

                from datetime import date
                if event.end_date and event.end_date < date.today():
                    logger.warning(f"Registration blocked: event {identifier} ended on {event.end_date}")
                    return None, None, "Event registration closed. This event has already ended."

                ticket_type_id = data.get("ticket_type_id")
                ticket_type = None

                if ticket_type_id:
                    ticket_type = TicketType.query.filter_by(id=ticket_type_id, event_id=event.id, is_active=True).first()
                    if not ticket_type:
                        return None, None, "Invalid ticket type"
                else:
                    ticket_type = TicketType.query.filter_by(event_id=event.id, is_active=True).order_by(TicketType.price.asc()).first()
                    if not ticket_type:
                        return None, None, "No active ticket types available for this event."

                discount_amount = Decimal("0.00")
                discount_code = data.get("discount_code")
                if discount_code:
                    discount, error = cls.validate_discount_code(identifier, discount_code, ticket_type_id)
                    if error:
                        return None, None, f"Discount code error: {error}"
                    if discount:
                        discount_amount = discount

                ticket_price = Decimal(str(ticket_type.price))
                final_price = max(ticket_price - discount_amount, Decimal("0.00"))

                if ticket_type.capacity and ticket_type.capacity > 0:
                    updated = db.session.query(TicketType).filter(
                        and_(TicketType.id == ticket_type.id,
                             func.coalesce(TicketType.available_seats, ticket_type.capacity) > 0)
                    ).update({
                        'available_seats': func.coalesce(TicketType.available_seats, ticket_type.capacity) - 1,
                        'version': TicketType.version + 1
                    })
                    if updated == 0:
                        raise SoldOutException(f"Ticket tier '{ticket_type.name}' is sold out")
                else:
                    db.session.query(TicketType).filter(TicketType.id == ticket_type.id).update({'version': TicketType.version + 1})

                if event.max_capacity > 0:
                    event_count = db.session.query(func.count(Registration.id)).filter_by(event_id=event.id).scalar()
                    if event_count >= event.max_capacity:
                        raise SoldOutException("The event has reached full capacity")

                existing = Registration.query.filter_by(event_id=event.id, user_id=user_id).first()
                if existing:
                    return None, None, "You are already registered for this event"

                reg_count = db.session.query(func.count(Registration.id)).filter_by(event_id=event.id).scalar() or 0
                sequence = reg_count + 1

                registration = Registration(
                    event_id=event.id, user_id=user_id, ticket_type_id=ticket_type.id,
                    full_name=data.get("full_name", "").strip(), email=data.get("email", "").strip().lower(),
                    phone=data.get("phone", "").strip(), nationality=data.get("nationality", "").strip(),
                    id_number=data.get("id_number", "").strip(), id_type=data.get("id_type", "national_id"),
                    ticket_type=ticket_type.name, registration_fee=float(ticket_type.price),
                    payment_status="free" if ticket_type.price == 0 else "pending",
                    registered_by="self", status="confirmed" if ticket_type.price == 0 else "pending_payment"
                )

                registration.generate_refs(event.slug, sequence)
                db.session.add(registration)
                db.session.flush()

                qr_code = cls._generate_qr_code(registration.qr_token, registration.registration_ref)

                logger.info(f"User {user_id} registered: {registration.registration_ref} (sequence {sequence})")
                db.session.commit()

                return cls._registration_to_dict(registration), qr_code, None

            except SoldOutException as e:
                raise e
            except Exception as e:
                logger.warning(f"Registration attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Max retries exceeded for registration: {e}")
                    return None, None, "Registration failed after multiple attempts. Please try again."

        return None, None, "Registration failed"

    @classmethod
    @with_transaction(isolation_level="REPEATABLE_READ")
    def add_to_waitlist(cls, identifier: str, user_id: int, data: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            Event = cls._get_event_model_class()
            Registration = cls._get_registration_class()
            Waitlist = cls._get_waitlist_class()
            TicketType = cls._get_ticket_type_class()

            event = Event.query.filter_by(slug=identifier, is_deleted=False).first()
            if not event:
                return None, "Event not found"

            existing_reg = Registration.query.filter_by(event_id=event.id, user_id=user_id).first()
            if existing_reg:
                return None, "You are already registered for this event"

            existing_waitlist = Waitlist.query.filter_by(event_id=event.id, user_id=user_id, status="pending").first()
            if existing_waitlist:
                return cls._waitlist_to_dict(existing_waitlist), "Already on waitlist"

            ticket_type_id = data.get("ticket_type_id")
            ticket_type = None
            if ticket_type_id:
                ticket_type = TicketType.query.filter_by(id=ticket_type_id, event_id=event.id).first()

            last_position = db.session.query(func.max(Waitlist.position)).filter_by(event_id=event.id, status="pending").scalar() or 0

            waitlist_entry = Waitlist(
                event_id=event.id, user_id=user_id, ticket_type_id=ticket_type.id if ticket_type else None,
                position=last_position + 1, email=data.get("email", ""), phone=data.get("phone", ""), status="pending"
            )

            db.session.add(waitlist_entry)
            db.session.flush()

            logger.info(f"User {user_id} added to waitlist for event {identifier} at position {waitlist_entry.position}")
            return cls._waitlist_to_dict(waitlist_entry), None

        except Exception as e:
            logger.error(f"Error adding to waitlist: {e}")
            return None, str(e)

    @classmethod
    def _waitlist_to_dict(cls, waitlist) -> Dict:
        return {
            "id": waitlist.id, "event_id": waitlist.event_id, "user_id": waitlist.user_id,
            "ticket_type_id": waitlist.ticket_type_id, "position": waitlist.position,
            "status": waitlist.status, "email": waitlist.email, "phone": waitlist.phone,
            "created_at": waitlist.created_at.isoformat() if waitlist.created_at else None,
            "notified_at": waitlist.notified_at.isoformat() if waitlist.notified_at else None,
            "converted_at": waitlist.converted_at.isoformat() if waitlist.converted_at else None,
        }

    @classmethod
    def register_for_event_with_payment(cls, identifier: str, user_id: int, data: Dict) -> Tuple[
        Optional[Dict], Optional[str], Optional[str]]:
        from decimal import Decimal

        try:
            with db.session.begin_nested():
                Event = cls._get_event_model_class()
                TicketType = cls._get_ticket_type_class()
                Registration = cls._get_registration_class()

                event = Event.query.with_for_update().filter_by(slug=identifier).first()
                if not event:
                    return None, None, "Event not found"

                from datetime import date
                if event.end_date and event.end_date < date.today():
                    logger.warning(f"Payment registration blocked: event {identifier} ended on {event.end_date}")
                    return None, None, "Event registration closed. This event has already ended."

                ticket_type_id = data.get("ticket_type_id")
                ticket_type = None

                if ticket_type_id:
                    ticket_type = TicketType.query.with_for_update().filter_by(id=ticket_type_id, event_id=event.id).first()
                    if not ticket_type:
                        return None, None, "Invalid ticket type"
                else:
                    ticket_type = TicketType.query.with_for_update().filter_by(event_id=event.id, price=0, is_active=True).first()
                    if not ticket_type:
                        return None, None, "No ticket type selected or available for registration."

                if ticket_type.capacity > 0:
                    current_count = db.session.query(db.func.count(Registration.id)).filter_by(ticket_type_id=ticket_type.id).scalar()
                    if current_count >= ticket_type.capacity:
                        return None, None, f"Ticket tier '{ticket_type.name}' is sold out"

                if event.max_capacity > 0:
                    event_count = db.session.query(db.func.count(Registration.id)).filter_by(event_id=event.id).scalar()
                    if event_count >= event.max_capacity:
                        return None, None, "Event has reached full capacity"

                existing = Registration.query.filter_by(event_id=event.id, user_id=user_id).first()
                if existing:
                    return None, None, "You are already registered for this event"

                fee = float(ticket_type.price)
                requires_payment = fee > 0

                payment_txn_id = None
                payment_status = "free"

                if requires_payment:
                    if not WalletService:
                        logger.error("WalletService not available for payment processing.")
                        return None, None, "Payment service temporarily unavailable. Please try again later."

                    try:
                        wallet_service = WalletService()
                        account = wallet_service.account_repo.get_by_user_id(user_id, event.currency)
                        if not account:
                            return None, None, f"No wallet found for {event.currency}"

                        client_request_id = f"EVT-REG-{identifier}-{user_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                        result = wallet_service.withdraw(
                            account_id=str(account.id), amount=Decimal(str(fee)), currency=event.currency,
                            client_request_id=client_request_id,
                            metadata={"event_slug": identifier, "event_name": event.name, "purpose": "event_ticket_purchase"}
                        )

                        if result.get("status") != "success":
                            error = result.get("error", "Payment failed")
                            logger.error(f"Payment failed for user {user_id}: {error}")
                            if "insufficient" in error.lower() or "balance" in error.lower():
                                return None, None, "Insufficient funds in your wallet. Please top up and try again."
                            return None, None, f"Payment failed: {error}"

                        payment_txn_id = result.get("transaction_id")
                        payment_status = "paid"
                        logger.info(f"Payment successful for user {user_id}: {payment_txn_id}")

                    except ImportError as e:
                        logger.error(f"WalletService import error: {e}")
                        return None, None, "Payment service configuration error."
                    except Exception as payment_error:
                        logger.error(f"Payment processing error for user {user_id}: {payment_error}", exc_info=True)
                        return None, None, "Payment processing failed. Please try again or contact support."

                last_reg = Registration.query.filter_by(event_id=event.id).order_by(Registration.id.desc()).first()
                sequence = (last_reg.id if last_reg else 0) + 1

                registration = Registration(
                    event_id=event.id, user_id=user_id, ticket_type_id=ticket_type.id,
                    full_name=data.get("full_name", "").strip(), email=data.get("email", "").strip().lower(),
                    phone=data.get("phone", "").strip(), nationality=data.get("nationality", "").strip(),
                    id_number=data.get("id_number", "").strip(), id_type=data.get("id_type", "national_id"),
                    ticket_type=ticket_type.name, registration_fee=fee, payment_status=payment_status,
                    wallet_txn_id=payment_txn_id, registered_by="self",
                    status="confirmed" if payment_status in ["paid", "free"] else "pending_payment"
                )

                registration.generate_refs(event.slug, sequence)
                db.session.add(registration)

                qr_code = cls._generate_qr_code(registration.qr_token, registration.registration_ref)

                logger.info(f"User {user_id} registered for {identifier} with payment {payment_status}")

                if SIGNALS_AVAILABLE:
                    try:
                        from flask import current_app
                        event_registered.send(current_app._get_current_object(), user_id=user_id,
                                             event_id=event.id, registration_id=registration.id,
                                             ticket_type=ticket_type.name)
                    except Exception as sig_error:
                        logger.warning(f"Failed to send event_registered signal: {sig_error}")

                return cls._registration_to_dict(registration), qr_code, None

        except Exception as e:
            logger.error(f"Registration with payment failed: {e}", exc_info=True)
            return None, None, "An unexpected error occurred during registration"

    @classmethod
    def check_in_attendee(cls, qr_token: str, checked_by_user_id: int) -> Tuple[bool, Optional[str], Optional[Dict]]:
        from datetime import datetime, timezone, date, timedelta
        import hmac
        import hashlib
        import os

        parts = qr_token.rsplit(':', 1)
        if len(parts) != 2:
            return False, "Invalid or tampered QR code", None
        payload, provided_sig = parts[0], parts[1]

        key = os.environ.get('QR_SECRET_KEY', 'dev-secret-change-in-production').encode()
        expected_sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:16]

        if not hmac.compare_digest(provided_sig, expected_sig):
            return False, "Invalid or tampered QR code", None

        payload_parts = payload.split(':')
        if len(payload_parts) < 2:
            return False, "Invalid QR code format", None
        reg_ref_from_payload = payload_parts[1]

        Registration = cls._get_registration_class()
        Event = cls._get_event_model_class()
        registration = Registration.query.filter_by(registration_ref=reg_ref_from_payload).first()

        if not registration:
            return False, "Invalid QR code", None

        event = Event.query.get(registration.event_id)
        if event and event.end_date:
            if date.today() > event.end_date + timedelta(days=1):
                return False, "This ticket has expired", None

        if registration.status == "checked_in":
            return False, f"Already checked in at {registration.checked_in_at.strftime('%Y-%m-%d %H:%M')}", None

        if registration.status == "cancelled":
            return False, "Registration has been cancelled", None

        registration.status = "checked_in"
        registration.checked_in_at = datetime.now(timezone.utc)
        registration.checked_in_by_id = checked_by_user_id

        db.session.commit()

        event = Event.query.get(registration.event_id)

        result = {
            "name": registration.full_name, "ticket_type": registration.ticket_type,
            "ticket_type_id": registration.ticket_type_id,
            "event_name": event.name if event else "Unknown",
            "event_start_date": event.start_date.isoformat() if event and event.start_date else None,
            "event_venue": event.venue if event else None, "registration_ref": registration.registration_ref,
            "photo_url": None, "nationality": registration.nationality, "phone": registration.phone,
            "checked_in_at": registration.checked_in_at.isoformat() if registration.checked_in_at else None,
        }

        logger.info(f"Checked in: {registration.registration_ref} by user {checked_by_user_id}")
        return True, f"Welcome {registration.full_name}! Successfully checked in.", result

    @classmethod
    def _generate_qr_code(cls, qr_token: str, registration_ref: str) -> str:
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr.add_data(qr_token)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/png;base64,{img_str}"

    @classmethod
    def _registration_to_dict(cls, registration) -> Dict:
        Event = cls._get_event_model_class()
        event = Event.query.get(registration.event_id)

        event_dict = {
            "id": event.public_id if event else None, "slug": event.slug if event else None,
            "name": event.name if event else None,
            "start_date": event.start_date.isoformat() if event and event.start_date else None,
            "end_date": event.end_date.isoformat() if event and event.end_date else None,
        } if event else {"id": None, "slug": None, "name": "Unknown Event", "start_date": None, "end_date": None}

        result = {
            "id": registration.id, "registration_ref": registration.registration_ref,
            "ticket_number": registration.ticket_number, "qr_token": registration.qr_token,
            "full_name": registration.full_name, "email": registration.email, "phone": registration.phone,
            "nationality": registration.nationality, "ticket_type": registration.ticket_type,
            "ticket_type_id": registration.ticket_type_id, "status": registration.status,
            "payment_status": registration.payment_status,
            "registration_fee": float(registration.registration_fee),
            "checked_in_at": registration.checked_in_at.isoformat() if registration.checked_in_at else None,
            "created_at": registration.created_at.isoformat() if registration.created_at else None,
            "event": event_dict,
        }

        if not result.get('ticket_number'):
            result['ticket_number'] = result['registration_ref']
        if result.get('qr_token'):
            result['qr_token_hint'] = result['qr_token'][:8] + '...'
            del result['qr_token']
        else:
            result['qr_token_hint'] = None
        if not result.get('status'):
            result['status'] = 'confirmed'
        if not result.get('payment_status'):
            result['payment_status'] = 'free'
        if not result.get('registration_fee'):
            result['registration_fee'] = 0.0
        if not result.get('ticket_type'):
            result['ticket_type'] = 'General Admission'
        if not result.get('event'):
            result['event'] = {"id": None, "slug": None, "name": "Unknown Event", "start_date": None, "end_date": None}

        if hasattr(registration, 'discount_code_applied'):
            result['discount_code_applied'] = registration.discount_code_applied
        if hasattr(registration, 'discount_amount'):
            result['discount_amount'] = float(registration.discount_amount) if registration.discount_amount else 0.0

        try:
            Assignment = cls._get_assignment_class()
            assignment = Assignment.query.filter_by(event_id=registration.event_id, attendee_id=registration.user_id).first()
            if assignment:
                result['assignment'] = cls._assignment_to_dict(assignment)
        except Exception as e:
            logger.warning(f"Could not load assignment for registration {registration.id}: {e}")

        return result

    # OPTIMIZED VERSION - Fixes N+1 queries
    @classmethod
    def get_attendee_dashboard_data(cls, user_id: int) -> Dict:
        from sqlalchemy.orm import joinedload
        from datetime import date

        Registration = cls._get_registration_class()
        Assignment = cls._get_assignment_class()

        # Query 1: Fetch all registrations with their events eagerly loaded (no N+1)
        all_registrations = Registration.query.options(
            joinedload(Registration.event)
        ).filter_by(user_id=user_id).all()

        # Query 2: Fetch all assignments for this user in ONE query
        assignments = Assignment.query.filter_by(attendee_id=user_id).all()

        # Create lookup map for O(1) access
        assignment_map = {assignment.event_id: cls._assignment_to_dict(assignment) for assignment in assignments}

        upcoming_registrations = []
        past_registrations = []
        attended_count = 0
        total_spent = 0.0

        for reg in all_registrations:
            event = reg.event  # Already loaded - NO extra query!
            if not event:
                continue

            reg_dict = cls._registration_to_dict_with_assignments(reg, assignment_map)

            if event.end_date and event.end_date >= date.today():
                upcoming_registrations.append(reg_dict)
            else:
                past_registrations.append(reg_dict)

            if reg.status == 'checked_in':
                attended_count += 1
            total_spent += float(reg.registration_fee or 0)

        upcoming_registrations.sort(key=lambda x: x['event']['start_date'] if x['event']['start_date'] else '9999-12-31')
        past_registrations.sort(key=lambda x: x['event']['start_date'] if x['event']['start_date'] else '0000-01-01', reverse=True)

        return {
            "upcoming_registrations": upcoming_registrations,
            "past_registrations": past_registrations,
            "upcoming_count": len(upcoming_registrations),
            "past_count": len(past_registrations),
            "attended_count": attended_count,
            "total_spent": f"{total_spent:.2f}"
        }

    @classmethod
    def _registration_to_dict_with_assignments(cls, registration, assignment_map: Dict = None) -> Dict:
        """Convert Registration model to dict WITHOUT extra database queries."""
        event = registration.event  # Already loaded - NO extra query!

        event_dict = {
            "id": event.public_id if event else None, "slug": event.slug if event else None,
            "name": event.name if event else None,
            "start_date": event.start_date.isoformat() if event and event.start_date else None,
            "end_date": event.end_date.isoformat() if event and event.end_date else None,
        } if event else {"id": None, "slug": None, "name": "Unknown Event", "start_date": None, "end_date": None}

        result = {
            "id": registration.id, "event_id": registration.event_id,
            "registration_ref": registration.registration_ref, "ticket_number": registration.ticket_number,
            "full_name": registration.full_name, "email": registration.email, "phone": registration.phone,
            "nationality": registration.nationality, "ticket_type": registration.ticket_type,
            "ticket_type_id": registration.ticket_type_id, "status": registration.status,
            "payment_status": registration.payment_status,
            "registration_fee": float(registration.registration_fee) if registration.registration_fee else 0.0,
            "checked_in_at": registration.checked_in_at.isoformat() if registration.checked_in_at else None,
            "created_at": registration.created_at.isoformat() if registration.created_at else None,
            "event": event_dict,
        }

        if assignment_map and registration.event_id in assignment_map:
            result['assignment'] = assignment_map[registration.event_id]

        if not result.get('ticket_number'):
            result['ticket_number'] = result['registration_ref']
        if not result.get('status'):
            result['status'] = 'confirmed'
        if not result.get('payment_status'):
            result['payment_status'] = 'free'
        if not result.get('ticket_type'):
            result['ticket_type'] = 'General Admission'

        return result

    @classmethod
    def get_event_model_by_id(cls, event_id: int):
        Event = cls._get_event_model_class()
        return Event.query.get(event_id)

    @classmethod
    def get_events_by_organisation(cls, organisation_id: int) -> List[Dict]:
        Event = cls._get_event_model_class()
        events = Event.query.filter_by(organisation_id=organisation_id).order_by(Event.created_at.desc()).all()
        return [cls._event_to_dict(event) for event in events]

    @classmethod
    def get_events_managed_by_user(cls, user_id: int) -> List[Dict]:
        from app.identity.models.user import User
        Event = cls._get_event_model_class()
        user = User.query.get(user_id)
        if not user:
            return []
        events = []
        user_events = Event.query.filter_by(organizer_id=user_id).all()
        events.extend(user_events)
        for membership in user.organisations:
            if user.has_org_role(membership.organisation_id, "org_owner", "org_admin"):
                org_events = Event.query.filter_by(organisation_id=membership.organisation_id).all()
                events.extend(org_events)
        unique_events = {e.id: e for e in events}.values()
        return [cls._event_to_dict(event) for event in unique_events]

    @classmethod
    def add_ticket_type(cls, identifier: str, data: Dict, user_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        event = cls.get_event_model(identifier)
        if not event:
            return None, "Event not found"
        if event.organizer_id != user_id:
            return None, "Unauthorized"
        try:
            TicketType = cls._get_ticket_type_class()
            ticket_type = TicketType(
                event_id=event.id, name=data["name"], description=data.get("description"),
                price=data.get("price", 0), capacity=data.get("capacity"),
                available_from=datetime.strptime(data["available_from"], "%Y-%m-%dT%H:%M") if data.get("available_from") else None,
                available_until=datetime.strptime(data["available_until"], "%Y-%m-%dT%H:%M") if data.get("available_until") else None,
                is_active=data.get("is_active", True)
            )
            db.session.add(ticket_type)
            db.session.commit()
            return cls._ticket_type_to_dict(ticket_type), None
        except Exception as e:
            db.session.rollback()
            return None, str(e)

    @classmethod
    def get_organizer_dashboard_data(cls, user_id: int) -> Dict:
        managed_events = cls.get_events_managed_by_user(user_id)
        Event = cls._get_event_model_class()
        Registration = cls._get_registration_class()
        event_models = Event.query.filter_by(organizer_id=user_id).all()
        total_registrations = 0
        total_revenue = 0.0
        active_events_list = []
        for event_model in event_models:
            reg_count = Registration.query.filter_by(event_id=event_model.id).count()
            reg_revenue = db.session.query(func.sum(Registration.registration_fee)).filter_by(
                event_id=event_model.id, payment_status='paid'
            ).scalar() or 0
            total_registrations += reg_count
            total_revenue += float(reg_revenue)
            if event_model.status in ['active', 'published']:
                event_dict = cls._event_to_dict(event_model)
                event_dict['registration_count'] = reg_count
                event_dict['revenue'] = float(reg_revenue)
                active_events_list.append(event_dict)
        return {
            "stats": {"total_events": len(managed_events), "total_registrations": total_registrations,
                     "total_revenue": f"{total_revenue:.2f}", "active_events": len(active_events_list)},
            "active_events": active_events_list[:5], "managed_events": managed_events
        }

    @classmethod
    def get_service_provider_dashboard_data(cls, user_id: int) -> Dict:
        from flask import current_app
        dashboard_data = {"user_properties": [], "user_vehicles": [], "relevant_events": [],
                         "event_assignments": [], "property_count": 0, "vehicle_count": 0}
        try:
            from app.events.signal_handlers import service_provider_data_requested
            responses = []
            def collect_response(sender, **kwargs):
                responses.append(kwargs)
            service_provider_data_requested.connect(collect_response, weak=False)
            service_provider_data_requested.send(current_app._get_current_object(), user_id=user_id, dashboard_data=dashboard_data)
            service_provider_data_requested.disconnect(collect_response)
            for response in responses:
                if 'properties' in response:
                    dashboard_data['user_properties'].extend(response['properties'])
                if 'vehicles' in response:
                    dashboard_data['user_vehicles'].extend(response['vehicles'])
                if 'event_assignments' in response:
                    dashboard_data['event_assignments'].extend(response['event_assignments'])
        except Exception as e:
            logger.warning(f"Could not collect service provider data via signals: {e}")
        service_cities = set()
        for prop in dashboard_data['user_properties']:
            if isinstance(prop, dict) and prop.get('city'):
                service_cities.add(prop['city'])
            elif hasattr(prop, 'city') and prop.city:
                service_cities.add(prop.city)
        for vehicle in dashboard_data['user_vehicles']:
            if isinstance(vehicle, dict) and vehicle.get('current_location'):
                service_cities.add(vehicle['current_location'])
            elif hasattr(vehicle, 'current_location') and vehicle.current_location:
                service_cities.add(vehicle.current_location)
        if service_cities:
            Event = cls._get_event_model_class()
            all_published_events = Event.query.filter(
                Event.status == EventStatus.PUBLISHED, Event.city.in_(list(service_cities))
            ).order_by(Event.start_date).limit(5).all()
            dashboard_data['relevant_events'] = [cls._event_to_dict(e) for e in all_published_events]
        dashboard_data['property_count'] = len(dashboard_data['user_properties'])
        dashboard_data['vehicle_count'] = len(dashboard_data['user_vehicles'])
        return dashboard_data

    @classmethod
    def register_for_event(cls, identifier: str, user_id: int, data: Dict) -> Tuple[Optional[Dict], Optional[str], Optional[str]]:
        use_optimistic = True
        if use_optimistic:
            return cls.register_for_event_optimistic(identifier, user_id, data)
        else:
            return cls._register_for_event_pessimistic(identifier, user_id, data)

    @classmethod
    def _register_for_event_pessimistic(cls, identifier: str, user_id: int, data: Dict) -> Tuple[Optional[Dict], Optional[str], Optional[str]]:
        from sqlalchemy import func
        try:
            with db.session.begin_nested():
                Event = cls._get_event_model_class()
                TicketType = cls._get_ticket_type_class()
                Registration = cls._get_registration_class()
                event = Event.query.with_for_update().filter_by(slug=identifier).first()
                if not event:
                    return None, None, "Event not found"
                ticket_type_id = data.get("ticket_type_id")
                ticket_type = None
                if ticket_type_id:
                    ticket_type = TicketType.query.with_for_update().filter_by(id=ticket_type_id, event_id=event.id).first()
                    if not ticket_type:
                        return None, None, "Invalid ticket type"
                else:
                    ticket_type = TicketType.query.with_for_update().filter_by(event_id=event.id, is_active=True).order_by(TicketType.price.asc()).first()
                    if not ticket_type:
                        return None, None, "No active ticket types available for this event."
                if ticket_type.capacity > 0:
                    if ticket_type.available_seats is None:
                        current_count = db.session.query(func.count(Registration.id)).filter_by(ticket_type_id=ticket_type.id).scalar()
                        ticket_type.available_seats = max(0, ticket_type.capacity - current_count)
                    if ticket_type.available_seats <= 0:
                        raise SoldOutException(f"Ticket tier '{ticket_type.name}' is sold out")
                    ticket_type.available_seats -= 1
                existing = Registration.query.filter_by(event_id=event.id, user_id=user_id).first()
                if existing:
                    return None, None, "You are already registered for this event"
                count = db.session.query(func.count(Registration.id)).filter_by(event_id=event.id).scalar()
                sequence = (count if count else 0) + 1
                registration = Registration(
                    event_id=event.id, user_id=user_id, ticket_type_id=ticket_type.id,
                    full_name=data.get("full_name", "").strip(), email=data.get("email", "").strip().lower(),
                    phone=data.get("phone", "").strip(), nationality=data.get("nationality", "").strip(),
                    id_number=data.get("id_number", "").strip(), id_type=data.get("id_type", "national_id"),
                    ticket_type=ticket_type.name, registration_fee=float(ticket_type.price),
                    payment_status="free" if ticket_type.price == 0 else "pending",
                    registered_by="self", status="confirmed" if ticket_type.price == 0 else "pending_payment"
                )
                registration.generate_refs(event.slug, sequence)
                db.session.add(registration)
                db.session.flush()
                qr_code = cls._generate_qr_code(registration.qr_token, registration.registration_ref)
                logger.info(f"User {user_id} registered: {registration.registration_ref}")
                if SIGNALS_AVAILABLE:
                    try:
                        from flask import current_app
                        from app.events.signal_handlers import event_registered, offer_services_after_registration
                        event_registered.send(current_app._get_current_object(), user_id=user_id, event_id=event.id,
                                             registration_id=registration.id, ticket_type=ticket_type.name)
                        offer_services_after_registration.send(current_app._get_current_object(), user_id=user_id,
                                                              event_id=event.id, event_slug=event.slug,
                                                              event_name=event.name, event_city=event.city,
                                                              event_start_date=event.start_date.isoformat() if event.start_date else None,
                                                              registration_id=registration.id)
                    except Exception as sig_error:
                        logger.warning(f"Failed to send signals: {sig_error}")
                return cls._registration_to_dict(registration), qr_code, None
        except Exception as e:
            if "sold out" in str(e).lower():
                logger.warning(f"Sold out: {e}")
                return None, None, str(e)
            logger.error(f"Registration failed: {e}", exc_info=True)
            return None, None, "An unexpected error occurred during registration"

    @classmethod
    def validate_discount_code(cls, identifier: str, code: str, ticket_type_id: Optional[int] = None) -> Tuple[Optional[Decimal], Optional[str]]:
        from decimal import Decimal
        event = cls.get_event_model(identifier)
        if not event:
            return None, "Event not found"
        TicketType = cls._get_ticket_type_class()
        ticket_type = None
        if ticket_type_id:
            ticket_type = TicketType.query.filter_by(id=ticket_type_id, event_id=event.id).first()
            if not ticket_type:
                return None, "Invalid ticket type"
        from app.events.models import DiscountCode
        discount = DiscountCode.query.filter_by(event_id=event.id, code=code.strip().upper(), is_active=True).first()
        if not discount:
            return None, "Invalid discount code"
        if not discount.is_valid():
            return None, "Discount code has expired or reached its usage limit"
        if ticket_type:
            ticket_price = Decimal(str(ticket_type.price))
        else:
            ticket_price = Decimal("0.00")
        discount_amount = discount.calculate_discount(ticket_price)
        discount.used_count = (discount.used_count or 0) + 1
        db.session.add(discount)
        logger.info(f"Discount code '{code}' validated for event '{identifier}': {discount_amount}")
        return discount_amount, None

    @classmethod
    def create_participation(cls, user_id: int, identifier: str, role: str = 'attendee',
                             control_mode: str = 'self_managed') -> Tuple[Optional[Dict], Optional[str]]:
        try:
            from app.events.models import Event, EventParticipation, ParticipationRole, ParticipationControlMode
            event = Event.query.filter_by(slug=identifier).first()
            if not event:
                return None, "Event not found"
            existing = EventParticipation.query.filter_by(event_id=event.id, user_id=user_id).first()
            if existing:
                return cls._participation_to_dict(existing), "Participation already exists"
            participation = EventParticipation(
                event_id=event.id, user_id=user_id, role=ParticipationRole(role),
                control_mode=ParticipationControlMode(control_mode), status='confirmed'
            )
            db.session.add(participation)
            db.session.commit()
            try:
                from app.audit.comprehensive_audit import AuditService
                AuditService.data_change(entity_type="event_participation", entity_id=str(participation.id),
                                        operation="create", old_value=None,
                                        new_value={"event_id": event.id, "user_id": user_id, "role": role, "control_mode": control_mode},
                                        changed_by=user_id, extra_data={"event_slug": identifier})
            except ImportError:
                logger.warning("AuditService not available, skipping audit log")
            logger.info(f"Participation created: user {user_id} for event {identifier} as {role}")
            return cls._participation_to_dict(participation), None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating participation: {e}")
            return None, str(e)

    @classmethod
    def assign_service_to_attendee(cls, attendee_id: int, identifier: str,
                                   booking_type: str, booking_id: int,
                                   managed_by: Optional[int] = None,
                                   notes: Optional[str] = None) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            from app.events.models import Event, EventAssignment, EventParticipation
            event = Event.query.filter_by(slug=identifier).first()
            if not event:
                return None, "Event not found"
            participation = EventParticipation.query.filter_by(event_id=event.id, user_id=attendee_id).first()
            if not participation:
                return None, "User is not participating in this event"
            assignment = EventAssignment.query.filter_by(event_id=event.id, attendee_id=attendee_id).first()
            if not assignment:
                assignment = EventAssignment(event_id=event.id, attendee_id=attendee_id, managed_by=managed_by, notes=notes)
                db.session.add(assignment)
            if booking_type == 'accommodation':
                assignment.accommodation_booking_id = booking_id
                try:
                    from app.accommodation.models.booking import AccommodationBooking
                    acc_booking = AccommodationBooking.query.get(booking_id)
                    if acc_booking:
                        acc_booking.event_id = event.id
                        acc_booking.event_participation_id = participation.id
                except ImportError:
                    logger.warning("Could not import AccommodationBooking, skipping event_id update")
            elif booking_type == 'transport':
                assignment.transport_booking_id = booking_id
                try:
                    from app.transport.models import Booking
                    transport_booking = Booking.query.get(booking_id)
                    if transport_booking:
                        transport_booking.event_id = event.id
                        transport_booking.event_participation_id = participation.id
                except ImportError:
                    logger.warning("Could not import Booking from transport.models, skipping event_id update")
            elif booking_type == 'meal':
                assignment.meal_booking_id = booking_id
            else:
                return None, f"Invalid booking type: {booking_type}"
            db.session.commit()
            try:
                from app.audit.comprehensive_audit import AuditService
                AuditService.data_change(entity_type="event_assignment", entity_id=str(assignment.id), operation="update",
                                        old_value=None,
                                        new_value={"event_id": event.id, "attendee_id": attendee_id,
                                                  f"{booking_type}_booking_id": booking_id, "managed_by": managed_by},
                                        changed_by=managed_by or attendee_id,
                                        extra_data={"event_slug": identifier, "booking_type": booking_type})
            except ImportError:
                logger.warning("AuditService not available, skipping audit log")
            logger.info(f"Service assigned: {booking_type} booking {booking_id} to attendee {attendee_id} for event {identifier}")
            return cls._assignment_to_dict(assignment), None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error assigning service to attendee: {e}")
            return None, str(e)

    @classmethod
    def _participation_to_dict(cls, participation) -> Dict:
        return {
            "id": participation.id, "event_id": participation.event_id, "user_id": participation.user_id,
            "role": participation.role.value if participation.role else None,
            "control_mode": participation.control_mode.value if participation.control_mode else None,
            "status": participation.status.value if participation.status else None,
            "joined_at": participation.joined_at.isoformat() if participation.joined_at else None,
            "left_at": participation.left_at.isoformat() if participation.left_at else None,
            "notes": participation.notes, "metadata": participation.metadata,
            "created_at": participation.created_at.isoformat() if participation.created_at else None,
            "updated_at": participation.updated_at.isoformat() if participation.updated_at else None,
        }

    @classmethod
    def _assignment_to_dict(cls, assignment) -> Dict:
        return {
            "id": assignment.id, "event_id": assignment.event_id, "attendee_id": assignment.attendee_id,
            "accommodation_booking_id": assignment.accommodation_booking_id,
            "transport_booking_id": assignment.transport_booking_id, "meal_booking_id": assignment.meal_booking_id,
            "managed_by": assignment.managed_by, "notes": assignment.notes, "schedule_json": assignment.schedule_json,
            "created_at": assignment.created_at.isoformat() if assignment.created_at else None,
            "updated_at": assignment.updated_at.isoformat() if assignment.updated_at else None,
        }

    @classmethod
    def get_event_participations(cls, identifier: str, role: Optional[str] = None) -> List[Dict]:
        try:
            from app.events.models import Event, EventParticipation
            event = Event.query.filter_by(slug=identifier).first()
            if not event:
                return []
            query = EventParticipation.query.filter_by(event_id=event.id)
            if role:
                query = query.filter_by(role=role)
            participations = query.order_by(EventParticipation.created_at.desc()).all()
            return [cls._participation_to_dict(participation) for participation in participations]
        except Exception as e:
            logger.error(f"Error getting event participations: {e}")
            return []

    @classmethod
    def get_event_assignments(cls, identifier: str) -> List[Dict]:
        try:
            from app.events.models import Event, EventAssignment
            event = Event.query.filter_by(slug=identifier).first()
            if not event:
                return []
            assignments = EventAssignment.query.filter_by(event_id=event.id).order_by(EventAssignment.created_at.desc()).all()
            return [cls._assignment_to_dict(assignment) for assignment in assignments]
        except Exception as e:
            logger.error(f"Error getting event assignments: {e}")
            return []

    @classmethod
    def get_attendee_assignments(cls, user_id: int) -> List[Dict]:
        try:
            from app.events.models import EventAssignment
            assignments = EventAssignment.query.filter_by(attendee_id=user_id).order_by(EventAssignment.created_at.desc()).all()
            return [cls._assignment_to_dict(assignment) for assignment in assignments]
        except Exception as e:
            logger.error(f"Error getting attendee assignments: {e}")
            return []

    @classmethod
    def cancel_registration(cls, registration_ref: str, user_id: int) -> Tuple[bool, Optional[str]]:
        from datetime import date
        Registration = cls._get_registration_class()
        TicketType = cls._get_ticket_type_class()
        registration = Registration.query.filter_by(registration_ref=registration_ref).first()
        if not registration:
            return False, "Registration not found"
        if registration.user_id != user_id:
            return False, "Unauthorized"
        if registration.status == "cancelled":
            return False, "Already cancelled"
        if registration.status == "checked_in":
            return False, "Cannot cancel a checked-in registration"
        event = cls.get_event_model_by_id(registration.event_id)
        if event and event.start_date and event.start_date < date.today():
            return False, "Cannot cancel past events"
        registration.status = "cancelled"
        if registration.ticket_type_id:
            ticket_type = TicketType.query.get(registration.ticket_type_id)
            if ticket_type and ticket_type.capacity and ticket_type.capacity > 0:
                ticket_type.available_seats = (ticket_type.available_seats or 0) + 1
                ticket_type.version = (ticket_type.version or 0) + 1
        db.session.commit()
        logger.info(f"Registration {registration_ref} cancelled by user {user_id}")
        return True, None

    @classmethod
    def build_event_context_json(cls, event_slug: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        from decimal import Decimal
        event = cls.get_event_model(event_slug)
        if not event:
            return {'event_found': False, 'event_slug': event_slug}
        Registration = cls._get_registration_class()
        total_regs = Registration.query.filter_by(event_id=event.id, status='confirmed').count()
        user_registered = False
        user_registration_ref = None
        if user_id:
            user_reg = Registration.query.filter_by(event_id=event.id, user_id=user_id, status='confirmed').first()
            if user_reg:
                user_registered = True
                user_registration_ref = user_reg.registration_ref
        remaining = None
        is_sold_out = False
        if event.max_capacity and event.max_capacity > 0:
            remaining = event.max_capacity - total_regs
            is_sold_out = remaining <= 0
        ticket_types = []
        is_free_event = True
        min_price = 0
        for tt in event.ticket_types:
            if not tt.is_active:
                continue
            tt_regs = len([r for r in tt.registrations if r.status == 'confirmed'])
            tt_remaining = tt.capacity - tt_regs if tt.capacity else None
            price = float(tt.price)
            if price > 0:
                is_free_event = False
                if min_price == 0 or price < min_price:
                    min_price = price
            ticket_types.append({
                'id': tt.id, 'name': tt.name, 'description': tt.description or '', 'price': price,
                'currency': event.currency, 'capacity': tt.capacity, 'remaining': tt_remaining,
                'is_sold_out': tt_remaining == 0 if tt_remaining is not None else False, 'is_active': tt.is_active,
            })
        return {
            'event_found': True, 'event_slug': event.slug, 'event_name': event.name,
            'event_description': event.description or '', 'event_category': event.category,
            'event_city': event.city, 'event_country': event.country, 'event_venue': event.venue or '',
            'event_start_date': event.start_date.isoformat() if event.start_date else None,
            'event_end_date': event.end_date.isoformat() if event.end_date else None,
            'event_currency': event.currency, 'event_status': event.status.value if event.status else None,
            'event_featured': event.featured, 'event_metadata': event.event_metadata or {},
            'contact_email': event.contact_email, 'contact_phone': event.contact_phone, 'website': event.website,
            'max_capacity': event.max_capacity or 0, 'total_registrations': total_regs,
            'remaining_capacity': remaining, 'is_sold_out': is_sold_out,
            'user_registered': user_registered, 'user_registration_ref': user_registration_ref,
            'can_register': event.status == EventStatus.PUBLISHED and not is_sold_out,
            'ticket_types': ticket_types, 'is_free_event': is_free_event, 'min_price': min_price,
        }

    @classmethod
    def build_event_context(cls, event_slug: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        from types import SimpleNamespace
        context = cls.build_event_context_json(event_slug, user_id)
        if not context.get('event_found'):
            return context
        context['event'] = SimpleNamespace(
            name=context['event_name'], description=context['event_description'], slug=context['event_slug'],
            city=context['event_city'], country=context['event_country'], venue=context['event_venue'],
            start_date=context['event_start_date'], end_date=context['event_end_date'],
            currency=context['event_currency'], status=context['event_status'], featured=context['event_featured'],
            website=context['website'], contact_email=context['contact_email'], contact_phone=context['contact_phone'],
            metadata=context['event_metadata'], max_capacity=context['max_capacity'], ticket_types=context['ticket_types'],
        )
        return context

    @classmethod
    def get_admin_dashboard_data(cls) -> Dict:
        try:
            Event = cls._get_event_model_class()
            Registration = cls._get_registration_class()
            total_events = Event.query.filter_by(is_deleted=False).count()
            published_events = Event.query.filter_by(status='published', is_deleted=False).count()
            pending_events = Event.query.filter_by(status='pending_approval', is_deleted=False).count()
            rejected_events = Event.query.filter_by(status='rejected', is_deleted=False).count()
            active_events = Event.query.filter_by(status='active', is_deleted=False).count()
            suspended_events = Event.query.filter_by(status='suspended', is_deleted=False).count()
            total_registrations = Registration.query.count()
            checked_in_registrations = Registration.query.filter_by(status='checked_in').count()
            return {
                'total_events': total_events, 'published_events': published_events,
                'pending_events': pending_events, 'rejected_events': rejected_events,
                'active_events': active_events, 'suspended_events': suspended_events,
                'total_registrations': total_registrations, 'checked_in_registrations': checked_in_registrations
            }
        except Exception as e:
            logger.error(f"Error in get_admin_dashboard_data: {e}", exc_info=True)
            return {
                'total_events': 0, 'published_events': 0, 'pending_events': 0,
                'rejected_events': 0, 'active_events': 0, 'suspended_events': 0,
                'total_registrations': 0, 'checked_in_registrations': 0
            }