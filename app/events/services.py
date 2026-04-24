# app/events/services.py - CORRECTED VERSION

"""
Event Service - DB-backed event management
Now using SQLAlchemy models instead of in-memory dict
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
import secrets
from flask import url_for, current_app
from app.extensions import db, redis_client
from app.events.models import Event, TicketType, EventRegistration, EventRole, Waitlist
from app.events.constants import EventStatus
# Remove tight coupling to accommodation module
# from app.accommodation.models.booking import AccommodationBooking
# BookingContextType may not exist, handle gracefully
try:
    from app.accommodation.models.booking import BookingContextType
except ImportError:
    # Create a fallback enum
    from enum import Enum
    class BookingContextType(Enum):
        EVENT = "event"
        TOURISM = "tourism"
        TRANSPORT = "transport"
        GENERAL = "general"
from sqlalchemy import func, case, and_
from decimal import Decimal

# ✅ DEFINE LOGGER FIRST (before any try/except blocks that use it)
logger = logging.getLogger(__name__)

# Legacy data protection layer
# Some database records may contain legacy status values not in EventStatus enum
def sanitize_status(status_value):
    """
    Safely convert any status value to a valid EventStatus enum value.
    Returns EventStatus.DRAFT.value for any unrecognized status.
    """
    from app.events.constants import EventStatus
    
    if status_value is None:
        return EventStatus.DRAFT.value
    
    # If it's already an EventStatus enum member
    if isinstance(status_value, EventStatus):
        return status_value.value
    
    # Try to match with EventStatus enum values
    status_str = str(status_value)
    try:
        return EventStatus(status_str).value
    except ValueError:
        # Log unrecognized status for monitoring
        logger.warning(f"Legacy status value encountered: '{status_str}', defaulting to DRAFT")
        return EventStatus.DRAFT.value

# Service provider data will be fetched via signals or separate services
# No direct imports to maintain loose coupling
Property = None
Vehicle = None

# Transaction utility
def with_transaction(isolation_level="REPEATABLE_READ"):
    """Decorator to ensure methods run within a database transaction."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Start a new transaction if not already in one
            if db.session.is_active:
                return func(*args, **kwargs)

            # Set isolation level
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
                # Restore original isolation level
                db.session.connection().connection.set_isolation_level(original_isolation)
        return wrapper
    return decorator

# Idempotency utility
class IdempotencyChecker:
    """Prevents duplicate processing of requests."""

    @staticmethod
    def check_and_store(key: str, ttl_seconds: int = 300) -> bool:
        """Check if request with this key was already processed."""
        if not redis_client:
            return False

        cache_key = f"idempotency:{key}"
        # Use SETNX to atomically check and set
        result = redis_client.set(cache_key, "1", nx=True, ex=ttl_seconds)
        return result is not True  # True means key already existed

    @staticmethod
    def generate_key(user_id: int, identifier: str, data_hash: str) -> str:
        """Generate idempotency key from request parameters."""
        import hashlib
        key_data = f"{user_id}:{identifier}:{data_hash}"
        return hashlib.sha256(key_data.encode()).hexdigest()

# Import wallet service at module level
try:
    from app.wallet.services.wallet_service import WalletService
except ImportError as e:
    logger.warning(f"WalletService not found: {e}. Wallet features may be limited.")
    WalletService = None

# Import signals for loose coupling
try:
    from app.events.signal_handlers import (
        event_registered,
        event_cancelled,
        event_capacity_released,
        offer_services_after_registration,
        service_provider_data_requested
    )
    SIGNALS_AVAILABLE = True
except ImportError:
    SIGNALS_AVAILABLE = False
    logger.warning("Signals not available - loose coupling features may be limited")



class SoldOutException(Exception):
    """Raised when an event or ticket type has reached its capacity"""
    pass


class EventService:
    """Event management with database persistence"""

    @classmethod
    def get_all_events(cls, status: str = None) -> List[Dict]:
        """Get all events, optionally filtered by status"""
        query = Event.query
        if status:
            # Sanitize the status parameter to ensure it's a valid EventStatus value
            sanitized_status = cls.sanitize_status(status)
            query = query.filter_by(status=sanitized_status)
        else:
            # Only show published events to public (not pending/rejected)
            query = query.filter_by(status=EventStatus.PUBLISHED)
        events = query.order_by(Event.start_date).all()
        return [cls._event_to_dict(event) for event in events]

    @classmethod
    def get_event(cls, event_id: str) -> Optional[Dict]:
        """Get a single event by slug"""
        event = Event.query.filter_by(slug=event_id).first()
        return cls._event_to_dict(event) if event else None

    @classmethod
    def change_event_status(cls, event_id: str, new_status: str, user_id: int, 
                           reason: str = None, ip_address: str = None, 
                           user_agent: str = None) -> Tuple[bool, Optional[str]]:
        """
        Centralized function to change event status with validation.
        Returns: (success, error_message)
        """
        from app.events.constants import EventStatus
        from app.events.models import EventModerationLog
        
        event = cls.get_event_model(event_id)
        if not event:
            return False, "Event not found"
        
        # Convert string to EventStatus enum if needed
        if isinstance(new_status, str):
            try:
                new_status = EventStatus(new_status)
            except ValueError:
                return False, f"Invalid status: {new_status}"
        
        # Define allowed state transitions
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
        
        # Check if transition is allowed
        if event.status not in ALLOWED_TRANSITIONS:
            return False, f"Cannot transition from status {event.status.value}"
        
        if new_status not in ALLOWED_TRANSITIONS[event.status]:
            return False, f"Cannot transition from {event.status.value} to {new_status.value}"
        
        # Map status changes to action names for logging
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
        
        # Update event status
        old_status = event.status
        event.status = new_status
        
        # Update timestamps based on status
        if new_status == EventStatus.APPROVED:
            event.approved_at = datetime.utcnow()
            event.approved_by_id = user_id
        elif new_status == EventStatus.REJECTED:
            event.rejected_at = datetime.utcnow()
            event.rejection_reason = reason
        
        # Create moderation log entry
        log_entry = EventModerationLog(
            event_id=event.id,
            user_id=user_id,
            action=action,
            from_status=old_status,
            to_status=new_status,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent
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
        """Create a new event with authorization checks"""
        try:
            from app.auth.helpers import has_global_role, has_org_role
            from app.identity.models.user import User
            from app.events.models import EventStatus
            import uuid

            user = User.query.get(user_id)
            if not user:
                return None, 'User not found'

            # System admins and event managers can create any type
            can_create_system = has_global_role(user, 'owner', 'super_admin', 'admin', 'event_manager')

            if creator_type == 'system' and not can_create_system:
                return None, 'Only system admins can create system events'

            if creator_type == 'organization':
                if not organization_id:
                    return None, 'Organization ID required'
                if not has_org_role(user, organization_id, 'org_owner', 'org_admin'):
                    return None, 'Not authorized to create events for this organization'

            # Generate slug from name
            slug = re.sub(r"[^a-z0-9]+", "-", data["name"].lower()).strip("-")

            # Ensure uniqueness
            original_slug = slug
            counter = 1
            while Event.query.filter_by(slug=slug).first():
                slug = f"{original_slug}-{counter}"
                counter += 1

            # Determine organizer_id based on creator_type
            if creator_type == 'organization':
                organizer_id = organization_id
            else:
                organizer_id = user_id

            # All new events default to pending_approval
            status = EventStatus.PENDING_APPROVAL
            approved_at = None
            approved_by_id = None

            # Auto-approve if event_manager creates
            if has_global_role(user, 'event_manager'):
                status = EventStatus.APPROVED
                approved_at = datetime.utcnow()
                approved_by_id = user_id

            event = Event(
                slug=slug,
                name=data["name"],
                description=data.get("description", ""),
                category=data.get("category", "other"),
                city=data["city"],
                country=data.get("country", "Uganda"),
                venue=data.get("venue", ""),
                start_date=datetime.strptime(data["start_date"], "%Y-%m-%d").date() if data.get("start_date") else None,
                end_date=datetime.strptime(data["end_date"], "%Y-%m-%d").date() if data.get("end_date") else None,
                # max_capacity and registration_fee are now handled by ticket types
                registration_required=data.get("registration_required", False),
                # registration_fee=data.get("registration_fee", 0), # Removed from Event model
                currency=data.get("currency", "USD"),
                organizer_id=organizer_id,
                website=data.get("website"),
                contact_email=data.get("contact_email"),
                contact_phone=data.get("contact_phone"),
                event_metadata=data.get("metadata", {}),
                status=status,
                # Add new ownership fields
                created_by_type=creator_type,
                organization_id=organization_id if creator_type == 'organization' else None,
                is_system_event=(creator_type == 'system'),
                original_creator_id=user_id,
                current_owner_type=creator_type,
                current_owner_id=organization_id if creator_type == 'organization' else user_id,
                approved_at=approved_at,
                approved_by_id=approved_by_id,
            )

            event.generate_ref()
            db.session.add(event)
            db.session.flush() # Get event.id for ticket types

            # Handle ticket types based on event_type
            if data.get("registration_required"):
                event_type = data.get("event_type", "free")
                if event_type == "free":
                    # Create a single free ticket type
                    ticket = TicketType(
                        event_id=event.id,
                        name="Free Admission",
                        price=0,
                        capacity=data.get("max_capacity"), # Use event's max_capacity for free events
                        is_active=True
                    )
                    db.session.add(ticket)
                elif event_type in ("paid", "ticketed") and data.get("ticket_tiers"):
                    # Create multiple ticket types from form data
                    for tier_data in data["ticket_tiers"]:
                        ticket = TicketType(
                            event_id=event.id,
                            name=tier_data["name"],
                            price=tier_data["price"],
                            capacity=tier_data["capacity"],
                            is_active=True
                        )
                        db.session.add(ticket)
                else:
                    db.session.rollback()
                    return None, "Invalid ticket configuration for ticketed event."

            db.session.commit()

            logger.info(f"Event created: {event.slug} by user {user_id} (type: {creator_type})")
            return cls._event_to_dict(event), None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating event: {e}")
            return None, str(e)

    @classmethod
    def update_event(cls, event_id: str, data: Dict, user_id: int) -> Tuple[bool, Optional[str]]:
        """Update an event"""
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

            event.updated_at = datetime.utcnow()
            db.session.commit()
            return True, None

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    @classmethod
    def delete_event(cls, event_id: str, user_id: int) -> Tuple[bool, Optional[str]]:
        """Delete an event if no registrations exist"""
        event = Event.query.filter_by(slug=event_id).first()
        if not event:
            return False, "Event not found"

        if event.organizer_id != user_id:
            return False, "Unauthorized"

        # Check for existing registrations instead of accommodation bookings
        registrations = EventRegistration.query.filter_by(
            event_id=event.id
        ).count()

        if registrations > 0:
            return False, f"Cannot delete event with {registrations} existing registrations"

        # Use soft delete instead of hard delete
        from sqlalchemy import func
        event.is_deleted = True
        event.deleted_at = func.now()
        event.deleted_by_id = user_id
        event.status = EventStatus.ARCHIVED

        db.session.commit()
        return True, None

    @classmethod
    def get_events_by_organizer(cls, organizer_id: int) -> List[Dict]:
        """Get events created by a specific organizer"""
        events = Event.query.filter_by(organizer_id=organizer_id).order_by(Event.created_at.desc()).all()
        return [cls._event_to_dict(event) for event in events]

    @classmethod
    def get_featured_event(cls) -> Optional[Dict]:
        """Get the featured event (only published)"""
        # Try featured flag first
        featured = Event.query.filter_by(featured=True, status=EventStatus.PUBLISHED).first()
        if featured:
            return cls._event_to_dict(featured)

        # Otherwise get next upcoming event
        from datetime import date
        upcoming = Event.query.filter(
            Event.status == EventStatus.PUBLISHED,
            Event.start_date >= date.today()
        ).order_by(Event.start_date).first()

        return cls._event_to_dict(upcoming) if upcoming else None

    @classmethod
    def get_upcoming_events(cls, limit: int = 3, exclude_featured: bool = False) -> List[Dict]:
        """Get upcoming events (only published ones)"""
        from datetime import date
        query = Event.query.filter(
            Event.status == EventStatus.PUBLISHED,
            Event.start_date >= date.today()
        ).order_by(Event.start_date)

        events = query.limit(limit + 1).all()

        if exclude_featured:
            featured = cls.get_featured_event()
            if featured:
                events = [e for e in events if e.slug != featured.get('slug')]

        return [cls._event_to_dict(event) for event in events[:limit]]

    @classmethod
    def get_event_stats(cls, event_id: str) -> Dict:
        """Get event statistics"""
        event = cls.get_event_model(event_id)
        if not event:
            return {}

        # Fetch registrations for this event
        registrations = EventRegistration.query.filter_by(event_id=event.id).all()

        total_registrations = len(registrations)
        total_revenue = sum(float(r.registration_fee) for r in registrations if r.payment_status == 'paid')
        checked_in_count = len([r for r in registrations if r.status == 'checked_in'])

        return {
            "event": cls._event_to_dict(event),
            "total_registrations": total_registrations,
            "total_revenue": total_revenue,
            "checked_in_count": checked_in_count,
        }

    @classmethod
    def get_event_model(cls, event_id: str) -> Optional[Event]:
        """Get the actual Event model instance"""
        return Event.query.filter_by(slug=event_id).first()

    @classmethod
    def approve_event(cls, event_id: str, admin_id: int) -> Tuple[bool, Optional[str]]:
        """Admin approves event"""
        event = cls.get_event_model(event_id)
        if not event:
            return False, "Event not found"

        event.status = EventStatus.PUBLISHED
        event.approved_at = datetime.utcnow()
        event.approved_by_id = admin_id

        # Clear any rejection fields if they exist
        event.rejected_at = None
        event.rejection_reason = None

        db.session.commit()
        logger.info(f"Event approved: {event.slug} by admin {admin_id}")
        return True, None

    @classmethod
    def reject_event(cls, event_id: str, admin_id: int, reason: str = None) -> Tuple[bool, Optional[str]]:
        """Admin rejects event"""
        event = cls.get_event_model(event_id)
        if not event:
            return False, "Event not found"

        event.status = EventStatus.REJECTED
        event.rejected_at = datetime.utcnow()
        event.rejection_reason = reason

        # Clear any approval fields if they exist
        event.approved_at = None
        event.approved_by_id = None

        db.session.commit()
        logger.info(f"Event rejected: {event.slug} by admin {admin_id}")
        return True, None

    @classmethod
    def _event_to_dict(cls, event: Event) -> Dict:
        """Convert Event model to dict"""
        # Normalize website field: empty string becomes None
        website = event.website
        if website == "":
            website = None

        # Apply status sanitizer at DB read boundary
        # This ensures legacy status values are converted to valid EventStatus values
        status_value = event.status.value if event.status else None
        sanitized_status = cls.sanitize_status(status_value) if status_value else None

        return {
            # Core fields
            "id": event.public_id,  # API consumers get UUID
            "slug": event.slug,  # Keep slug for browser URLs
            "event_ref": event.event_ref,
            "name": event.name,
            "description": event.description,
            "category": event.category,
            "city": event.city,
            "country": event.country,
            "venue": event.venue,

            # Dates
            "start_date": event.start_date.isoformat() if event.start_date else None,
            "end_date": event.end_date.isoformat() if event.end_date else None,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "updated_at": event.updated_at.isoformat() if event.updated_at else None,

            # Capacity & Registration
            "max_capacity": event.max_capacity, # Still exists in model, but primary capacity check is on ticket_type
            "registration_required": event.registration_required,
            "registration_fee": float(event.registration_fee) if event.registration_fee else 0, # Still exists in model, but primary fee is on ticket_type
            "currency": event.currency,

            # Status - use sanitized value
            "status": sanitized_status,
            "featured": event.featured,

            # Ownership
            "organizer_id": event.organizer_id,

            # Contact & Media
            "website": website,
            "contact_email": event.contact_email,
            "contact_phone": event.contact_phone,
            "metadata": event.event_metadata or {},

            # Approval Workflow Fields
            "approved_at": event.approved_at.isoformat() if event.approved_at else None,
            "rejected_at": event.rejected_at.isoformat() if event.rejected_at else None,
            "rejection_reason": event.rejection_reason,

            # Ticket Types
            "ticket_types": [cls._ticket_type_to_dict(tt) for tt in event.ticket_types] if event.ticket_types else []
        }

    @classmethod
    def _ticket_type_to_dict(cls, ticket_type: TicketType) -> Dict:
        """Convert TicketType model to dict"""
        # Count registrations for this specific ticket type
        reg_count = EventRegistration.query.filter_by(ticket_type_id=ticket_type.id).count()

        return {
            "id": ticket_type.id,
            "name": ticket_type.name,
            "description": ticket_type.description,
            "price": float(ticket_type.price),
            "capacity": ticket_type.capacity,
            "registration_count": reg_count,
            "available_from": ticket_type.available_from.isoformat() if ticket_type.available_from else None,
            "available_until": ticket_type.available_until.isoformat() if ticket_type.available_until else None,
            "is_active": ticket_type.is_active
        }

    @classmethod
    def get_registration_count(cls, event_id: str, ticket_type_id: int = None) -> int:
        """Get number of registrations for an event, optionally filtered by ticket type"""
        event = cls.get_event_model(event_id)
        if not event:
            return 0
        query = EventRegistration.query.filter_by(event_id=event.id)
        if ticket_type_id:
            query = query.filter_by(ticket_type_id=ticket_type_id)
        return query.count()

    @classmethod
    def get_registrations_by_event(cls, event_id: str, status: str = None) -> List[Dict]:
        """Get all registrations for an event"""
        event = cls.get_event_model(event_id)
        if not event:
            return []

        query = EventRegistration.query.filter_by(event_id=event.id)
        if status:
            query = query.filter_by(status=status)

        registrations = query.order_by(EventRegistration.created_at.desc()).all()
        return [cls._registration_to_dict(reg) for reg in registrations]

    @classmethod
    def get_user_registrations(cls, user_id: int) -> List[Dict]:
        """Get all registrations for a user"""
        registrations = EventRegistration.query.filter_by(user_id=user_id).order_by(
            EventRegistration.created_at.desc()
        ).all()
        return [cls._registration_to_dict(reg) for reg in registrations]

    @classmethod
    @with_transaction(isolation_level="REPEATABLE_READ")
    def register_for_event_optimistic(cls, identifier: str, user_id: int, data: Dict,
                                     idempotency_key: str = None, max_retries: int = 3) -> Tuple[
        Optional[Dict], Optional[str], Optional[str]]:
        """
        Register a user for an event with optimistic concurrency control.
        Better for high-traffic scenarios like AFCON.
        Returns: (registration_dict, qr_code_base64, error_message)
        """
        from sqlalchemy import func, and_
        from decimal import Decimal

        # Check idempotency
        if idempotency_key:
            if IdempotencyChecker.check_and_store(idempotency_key):
                logger.warning(f"Duplicate registration attempt detected: {idempotency_key}")
                # Try to find existing registration
                # First get the event to get its ID
                event = Event.query.filter_by(slug=identifier).first()
                if event:
                    existing_reg = EventRegistration.query.filter_by(
                        event_id=event.id,
                        user_id=user_id
                    ).first()
                else:
                    existing_reg = None
                if existing_reg:
                    qr_code = cls._generate_qr_code(existing_reg.qr_token, existing_reg.registration_ref)
                    return cls._registration_to_dict(existing_reg), qr_code, "Duplicate request - registration already processed"
                return None, None, "Duplicate request"

        # Generate idempotency key if not provided
        if not idempotency_key:
            data_hash = hashlib.sha256(str(sorted(data.items())).encode()).hexdigest()
            idempotency_key = IdempotencyChecker.generate_key(user_id, identifier, data_hash)

        for attempt in range(max_retries):
            try:
                    # 1. Fetch event (no lock needed for optimistic approach)
                    event = Event.query.filter_by(slug=identifier).first()
                    if not event:
                        return None, None, "Event not found"

                    # 2. Identify the ticket type
                    ticket_type_id = data.get("ticket_type_id")
                    ticket_type = None

                    if ticket_type_id:
                        ticket_type = TicketType.query.filter_by(
                            id=ticket_type_id,
                            event_id=event.id,
                            is_active=True
                        ).first()
                        if not ticket_type:
                            return None, None, "Invalid ticket type"
                    else:
                        ticket_type = TicketType.query.filter_by(
                            event_id=event.id,
                            is_active=True
                        ).order_by(TicketType.price.asc()).first()
                        if not ticket_type:
                            return None, None, "No active ticket types available for this event."

                    # 3. Validate discount code if present
                    discount_amount = Decimal("0.00")
                    discount_code = data.get("discount_code")
                    if discount_code:
                        discount, error = cls.validate_discount_code(identifier, discount_code, ticket_type_id)
                        if error:
                            return None, None, f"Discount code error: {error}"
                        if discount:
                            discount_amount = discount

                    # Calculate final price after discount
                    ticket_price = Decimal(str(ticket_type.price))
                    final_price = max(ticket_price - discount_amount, Decimal("0.00"))

                    # 4. Handle capacity with atomic SQL update
                    # If capacity is 0 or None, it's unlimited - skip capacity checks
                    if ticket_type.capacity and ticket_type.capacity > 0:
                        # Use atomic update to decrement available_seats
                        # This ensures thread-safety without explicit locking
                        # Handle NULL available_seats by coalescing to capacity
                        updated = db.session.query(TicketType).filter(
                            and_(
                                TicketType.id == ticket_type.id,
                                # Check if there are available seats (handling NULL)
                                func.coalesce(TicketType.available_seats, ticket_type.capacity) > 0
                            )
                        ).update({
                            'available_seats': func.coalesce(TicketType.available_seats, ticket_type.capacity) - 1,
                            'version': TicketType.version + 1
                        })

                        if updated == 0:
                            # No rows updated means no available seats
                            raise SoldOutException(f"Ticket tier '{ticket_type.name}' is sold out")
                    else:
                        # Unlimited capacity - just update version for consistency
                        db.session.query(TicketType).filter(
                            TicketType.id == ticket_type.id
                        ).update({
                            'version': TicketType.version + 1
                        })

                    # 4. Check event-level capacity
                    if event.max_capacity > 0:
                        event_count = db.session.query(func.count(EventRegistration.id)).filter_by(
                            event_id=event.id
                        ).scalar()
                        if event_count >= event.max_capacity:
                            raise SoldOutException("The event has reached full capacity")

                    # 5. Check if user already registered
                    existing = EventRegistration.query.filter_by(
                        event_id=event.id,
                        user_id=user_id
                    ).first()
                    if existing:
                        return None, None, "You are already registered for this event"

                    # 6. Create registration
                    # Get the next sequence number safely using count
                    from sqlalchemy import func
                    count = db.session.query(func.count(EventRegistration.id)).filter_by(
                        event_id=event.id
                    ).scalar()
                    sequence = (count if count else 0) + 1

                    # Prepare registration data
                    registration_data = {
                        'event_id': event.id,
                        'user_id': user_id,
                        'ticket_type_id': ticket_type.id,
                        'full_name': data.get("full_name", "").strip(),
                        'email': data.get("email", "").strip().lower(),
                        'phone': data.get("phone", "").strip(),
                        'nationality': data.get("nationality", "").strip(),
                        'id_number': data.get("id_number", "").strip(),
                        'id_type': data.get("id_type", "national_id"),
                        'ticket_type': ticket_type.name,
                        'registration_fee': float(final_price),
                        'payment_status': "free" if final_price == 0 else "pending",
                        'registered_by': "self",
                        'status': "confirmed" if final_price == 0 else "pending_payment",
                    }

                    # Add discount fields if applicable
                    if discount_code:
                        registration_data['discount_code_applied'] = discount_code
                        registration_data['discount_amount'] = float(discount_amount)

                    registration = EventRegistration(**registration_data)

                    registration.generate_refs(event.slug, sequence)
                    db.session.add(registration)

                    # Flush to get ID but don't commit yet
                    db.session.flush()

                    # Generate QR code
                    qr_code = cls._generate_qr_code(registration.qr_token, registration.registration_ref)

                    logger.info(f"User {user_id} registered: {registration.registration_ref} (attempt {attempt + 1})")

                    # Send signal for loose coupling
                    if SIGNALS_AVAILABLE:
                        try:
                            from flask import current_app
                            # Use signal_handlers instead of signals
                            from app.events.signal_handlers import event_registered, offer_services_after_registration

                            # Emit registration signal
                            event_registered.send(
                                current_app._get_current_object(),
                                user_id=user_id,
                                event_id=event.id,
                                registration_id=registration.id,
                                ticket_type=ticket_type.name
                            )

                            # Emit service offering signal
                            offer_services_after_registration.send(
                                current_app._get_current_object(),
                                user_id=user_id,
                                event_id=event.id,
                                event_slug=event.slug,
                                event_name=event.name,
                                event_city=event.city,
                                event_start_date=event.start_date.isoformat() if event.start_date else None,
                                registration_id=registration.id
                            )
                        except Exception as sig_error:
                            logger.warning(f"Failed to send signals: {sig_error}")

                    return cls._registration_to_dict(registration), qr_code, None

            except SoldOutException as e:
                # Re-raise sold out exceptions immediately
                raise e
            except Exception as e:
                logger.warning(f"Registration attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Max retries exceeded for registration: {e}")
                    return None, None, "Registration failed after multiple attempts. Please try again."
                # Continue to next attempt

        return None, None, "Registration failed"

    @classmethod
    @with_transaction(isolation_level="REPEATABLE_READ")
    def add_to_waitlist(cls, identifier: str, user_id: int, data: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Add user to waitlist when event is sold out.
        Returns: (waitlist_entry_dict, error_message)
        """
        try:
            event = Event.query.filter_by(slug=identifier, is_deleted=False).first()
            if not event:
                return None, "Event not found"

            # Check if user is already registered
            existing_reg = EventRegistration.query.filter_by(
                event_id=event.id,
                user_id=user_id
            ).first()
            if existing_reg:
                return None, "You are already registered for this event"

            # Check if user is already on waitlist
            existing_waitlist = Waitlist.query.filter_by(
                event_id=event.id,
                user_id=user_id,
                status="pending"
            ).first()
            if existing_waitlist:
                return cls._waitlist_to_dict(existing_waitlist), "Already on waitlist"

            # Get ticket type if specified
            ticket_type_id = data.get("ticket_type_id")
            ticket_type = None
            if ticket_type_id:
                ticket_type = TicketType.query.filter_by(
                    id=ticket_type_id,
                    event_id=event.id
                ).first()

            # Calculate position (last position + 1)
            last_position = db.session.query(func.max(Waitlist.position)).filter_by(
                event_id=event.id,
                status="pending"
            ).scalar() or 0

            waitlist_entry = Waitlist(
                event_id=event.id,
                user_id=user_id,
                ticket_type_id=ticket_type.id if ticket_type else None,
                position=last_position + 1,
                email=data.get("email", ""),
                phone=data.get("phone", ""),
                status="pending"
            )

            db.session.add(waitlist_entry)
            db.session.flush()

            logger.info(f"User {user_id} added to waitlist for event {identifier} at position {waitlist_entry.position}")

            return cls._waitlist_to_dict(waitlist_entry), None

        except Exception as e:
            logger.error(f"Error adding to waitlist: {e}")
            return None, str(e)

    @classmethod
    def _waitlist_to_dict(cls, waitlist: Waitlist) -> Dict:
        """Convert Waitlist model to dict."""
        return {
            "id": waitlist.id,
            "event_id": waitlist.event_id,
            "user_id": waitlist.user_id,
            "ticket_type_id": waitlist.ticket_type_id,
            "position": waitlist.position,
            "status": waitlist.status,
            "email": waitlist.email,
            "phone": waitlist.phone,
            "created_at": waitlist.created_at.isoformat() if waitlist.created_at else None,
            "notified_at": waitlist.notified_at.isoformat() if waitlist.notified_at else None,
            "converted_at": waitlist.converted_at.isoformat() if waitlist.converted_at else None,
        }

    @classmethod
    def register_for_event_with_payment(cls, identifier: str, user_id: int, data: Dict) -> Tuple[
        Optional[Dict], Optional[str], Optional[str]]:
        """
        Register a user for an event with wallet payment processing.
        Returns: (registration_dict, payment_required, error_message)
        """
        from decimal import Decimal

        try:
            # Start transaction
            with db.session.begin_nested():
                # Get event with lock
                event = Event.query.with_for_update().filter_by(slug=identifier).first()
                if not event:
                    return None, None, "Event not found"

                # Get ticket type WITH LOCK
                ticket_type_id = data.get("ticket_type_id")
                ticket_type = None

                if ticket_type_id:
                    ticket_type = TicketType.query.with_for_update().filter_by(
                        id=ticket_type_id,
                        event_id=event.id
                    ).first()
                    if not ticket_type:
                        return None, None, "Invalid ticket type"
                else:
                    # Find first free active ticket
                    ticket_type = TicketType.query.with_for_update().filter_by(
                        event_id=event.id,
                        price=0,
                        is_active=True
                    ).first()
                    if not ticket_type:
                        return None, None, "No ticket type selected or available for registration."

                # Check capacity atomically
                if ticket_type.capacity > 0:
                    current_count = db.session.query(db.func.count(EventRegistration.id)).filter_by(
                        ticket_type_id=ticket_type.id
                    ).scalar()
                    if current_count >= ticket_type.capacity:
                        return None, None, f"Ticket tier '{ticket_type.name}' is sold out"

                if event.max_capacity > 0:
                    event_count = db.session.query(db.func.count(EventRegistration.id)).filter_by(
                        event_id=event.id
                    ).scalar()
                    if event_count >= event.max_capacity:
                        return None, None, "Event has reached full capacity"

                # Check existing registration
                existing = EventRegistration.query.filter_by(
                    event_id=event.id,
                    user_id=user_id
                ).first()
                if existing:
                    return None, None, "You are already registered for this event"

                # Calculate fee
                fee = float(ticket_type.price)
                requires_payment = fee > 0

                # Process payment if required
                payment_txn_id = None
                payment_status = "free"

                if requires_payment:
                    if not WalletService:
                        logger.error("WalletService not available for payment processing.")
                        return None, None, "Payment service temporarily unavailable. Please try again later."

                    try:
                        # WalletService is a class, we need to instantiate it or call static methods
                        # Check if it has a static debit method
                        if hasattr(WalletService, 'debit'):
                            success, result, error = WalletService.debit(
                                user_id=user_id,
                                amount=Decimal(str(fee)),
                                currency=event.currency,
                                reference=f"EVT-REG-{identifier}-{user_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                                description=f"Registration for {event.name}",
                                metadata={"event_slug": identifier, "event_name": event.name}
                            )
                        else:
                            # Try to instantiate
                            wallet_service = WalletService()
                            success, result, error = wallet_service.debit(
                                user_id=user_id,
                                amount=Decimal(str(fee)),
                                currency=event.currency,
                                reference=f"EVT-REG-{identifier}-{user_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                                description=f"Registration for {event.name}",
                                metadata={"event_slug": identifier, "event_name": event.name}
                            )

                        if not success:
                            logger.error(f"Payment failed for user {user_id}: {error}")
                            # Check if it's a balance issue
                            if "insufficient" in error.lower() or "balance" in error.lower():
                                return None, None, "Insufficient funds in your wallet. Please top up and try again."
                            return None, None, f"Payment failed: {error}"

                        payment_txn_id = result.get("transaction_id") if result else None
                        payment_status = "paid"

                        # Log successful payment
                        logger.info(f"Payment successful for user {user_id}: {payment_txn_id}")

                    except ImportError as e:
                        logger.error(f"WalletService import error: {e}")
                        return None, None, "Payment service configuration error."
                    except Exception as payment_error:
                        logger.error(f"Payment processing error for user {user_id}: {payment_error}", exc_info=True)
                        # Attempt to refund if transaction was created but registration failed
                        # This would require a separate refund mechanism
                        return None, None, "Payment processing failed. Please try again or contact support."

                # Create registration
                last_reg = EventRegistration.query.filter_by(event_id=event.id).order_by(
                    EventRegistration.id.desc()
                ).first()
                sequence = (last_reg.id if last_reg else 0) + 1

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
                    payment_status=payment_status,
                    wallet_txn_id=payment_txn_id,
                    registered_by="self",
                    status="confirmed" if payment_status in ["paid", "free"] else "pending_payment"
                )

                registration.generate_refs(event.slug, sequence)
                db.session.add(registration)

                # Generate QR code
                qr_code = cls._generate_qr_code(registration.qr_token, registration.registration_ref)

                logger.info(f"User {user_id} registered for {identifier} with payment {payment_status}")

                # Send signal for loose coupling
                if SIGNALS_AVAILABLE:
                    try:
                        from flask import current_app
                        event_registered.send(
                            current_app._get_current_object(),
                            user_id=user_id,
                            event_id=event.id,
                            registration_id=registration.id,
                            ticket_type=ticket_type.name
                        )
                    except Exception as sig_error:
                        logger.warning(f"Failed to send event_registered signal: {sig_error}")

                return cls._registration_to_dict(registration), qr_code, None

        except Exception as e:
            logger.error(f"Registration with payment failed: {e}", exc_info=True)
            return None, None, "An unexpected error occurred during registration"

    @classmethod
    def check_in_attendee(cls, qr_token: str, checked_by_user_id: int) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Check in an attendee using QR token.
        Returns: (success, message, registration_dict)
        """
        from datetime import datetime, date, timedelta
        import hmac
        import hashlib
        import os

        # --- HMAC verification ---
        # Parse the token: payload:signature
        parts = qr_token.rsplit(':', 1)
        if len(parts) != 2:
            return False, "Invalid or tampered QR code", None
        payload, provided_sig = parts[0], parts[1]

        key = os.environ.get('QR_SECRET_KEY', 'dev-secret-change-in-production').encode()
        expected_sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:16]

        if not hmac.compare_digest(provided_sig, expected_sig):
            return False, "Invalid or tampered QR code", None

        # --- Expiry check ---
        # Extract registration_ref from payload (format: AFCON360:reg_ref:sequence)
        payload_parts = payload.split(':')
        if len(payload_parts) < 2:
            return False, "Invalid QR code format", None
        reg_ref_from_payload = payload_parts[1]

        registration = EventRegistration.query.filter_by(registration_ref=reg_ref_from_payload).first()

        if not registration:
            return False, "Invalid QR code", None

        # Expiry check based on event end_date
        event = Event.query.get(registration.event_id)
        if event and event.end_date:
            if date.today() > event.end_date + timedelta(days=1):
                return False, "This ticket has expired", None

        if registration.status == "checked_in":
            return False, f"Already checked in at {registration.checked_in_at.strftime('%Y-%m-%d %H:%M')}", None

        if registration.status == "cancelled":
            return False, "Registration has been cancelled", None

        # Check in
        registration.status = "checked_in"
        registration.checked_in_at = datetime.utcnow()
        registration.checked_in_by_id = checked_by_user_id

        db.session.commit()

        # Get event name for response
        event = Event.query.get(registration.event_id)

        result = {
            "name": registration.full_name,
            "ticket_type": registration.ticket_type,
            "ticket_type_id": registration.ticket_type_id,
            "event_name": event.name if event else "Unknown",
            "event_start_date": event.start_date.isoformat() if event and event.start_date else None,
            "event_venue": event.venue if event else None,
            "registration_ref": registration.registration_ref,
            "photo_url": None,
            "nationality": registration.nationality,
            "phone": registration.phone,
            "checked_in_at": registration.checked_in_at.isoformat() if registration.checked_in_at else None,
        }

        logger.info(f"Checked in: {registration.registration_ref} by user {checked_by_user_id}")

        return True, f"Welcome {registration.full_name}! Successfully checked in.", result

    @classmethod
    def _generate_qr_code(cls, qr_token: str, registration_ref: str) -> str:
        """Generate QR code as base64 string"""
        # Encode only the qr_token string itself (signed payload)
        # This makes QR work offline and hides server structure
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_token)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        return f"data:image/png;base64,{img_str}"

    @classmethod
    def _registration_to_dict(cls, registration) -> Dict:
        """Convert Registration model to dict"""
        event = Event.query.get(registration.event_id)

        # Always provide an event dict (never None) so templates can safely access .name etc.
        event_dict = {
            "id": event.public_id if event else None,
            "slug": event.slug if event else None,
            "name": event.name if event else None,
            "start_date": event.start_date.isoformat() if event and event.start_date else None,
            "end_date": event.end_date.isoformat() if event and event.end_date else None,
        }

        result = {
            "id": registration.id,
            "registration_ref": registration.registration_ref,
            "ticket_number": registration.ticket_number,
            "qr_token": registration.qr_token,
            "full_name": registration.full_name,
            "email": registration.email,
            "phone": registration.phone,
            "nationality": registration.nationality,
            "ticket_type": registration.ticket_type,
            "ticket_type_id": registration.ticket_type_id,
            "status": registration.status,
            "payment_status": registration.payment_status,
            "registration_fee": float(registration.registration_fee),
            "checked_in_at": registration.checked_in_at.isoformat() if registration.checked_in_at else None,
            "created_at": registration.created_at.isoformat() if registration.created_at else None,
            "event": event_dict,
        }

        # Ensure ticket_number is always present (fallback to registration_ref if missing)
        if not result.get('ticket_number'):
            result['ticket_number'] = result['registration_ref']

        # Do NOT expose full qr_token via API — show only first 8 chars for debugging
        if result.get('qr_token'):
            result['qr_token_hint'] = result['qr_token'][:8] + '...'
            del result['qr_token']
        else:
            result['qr_token_hint'] = None

        # Ensure status is always present
        if not result.get('status'):
            result['status'] = 'confirmed'

        # Ensure payment_status is always present
        if not result.get('payment_status'):
            result['payment_status'] = 'free'

        # Ensure registration_fee is always present
        if not result.get('registration_fee'):
            result['registration_fee'] = 0.0

        # Ensure ticket_type is always present
        if not result.get('ticket_type'):
            result['ticket_type'] = 'General Admission'

        # Ensure event dict is always present
        if not result.get('event'):
            result['event'] = {
                "id": None,
                "slug": None,
                "name": "Unknown Event",
                "start_date": None,
                "end_date": None
            }

        # Add discount fields if they exist
        if hasattr(registration, 'discount_code_applied'):
            result['discount_code_applied'] = registration.discount_code_applied
        if hasattr(registration, 'discount_amount'):
            result['discount_amount'] = float(registration.discount_amount) if registration.discount_amount else 0.0

        # Add assignment data if it exists
        try:
            from app.events.models import EventAssignment
            assignment = EventAssignment.query.filter_by(
                event_id=registration.event_id,
                attendee_id=registration.user_id
            ).first()
            
            if assignment:
                result['assignment'] = cls._assignment_to_dict(assignment)
        except Exception as e:
            logger.warning(f"Could not load assignment for registration {registration.id}: {e}")

        return result

    # Get Event by ID

    @classmethod
    def get_event_model_by_id(cls, event_id: int) -> Optional[Event]:
        """Get Event model by database ID"""
        return Event.query.get(event_id)

    @classmethod
    def get_events_by_organisation(cls, organisation_id: int) -> List[Dict]:
        """Get all events for a specific organization"""
        events = Event.query.filter_by(organisation_id=organisation_id).order_by(Event.created_at.desc()).all()
        return [cls._event_to_dict(event) for event in events]

    @classmethod
    def get_events_managed_by_user(cls, user_id: int) -> List[Dict]:
        """
        Get all events a user can manage:
        - Events they created
        - Events for organizations they admin
        """
        from app.identity.models.user import User
        user = User.query.get(user_id)

        if not user:
            return []

        events = []

        # Events user created as individual
        user_events = Event.query.filter_by(organizer_id=user_id).all()
        events.extend(user_events)

        # Events for organizations user admins
        for membership in user.organisations:
            if user.has_org_role(membership.organisation_id, "org_owner", "org_admin"):
                org_events = Event.query.filter_by(organisation_id=membership.organisation_id).all()
                events.extend(org_events)

        # Remove duplicates
        unique_events = {e.id: e for e in events}.values()

        return [cls._event_to_dict(event) for event in unique_events]

    @classmethod
    def add_ticket_type(cls, identifier: str, data: Dict, user_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Add a new ticket type to an event"""
        event = cls.get_event_model(identifier)
        if not event:
            return None, "Event not found"

        if event.organizer_id != user_id:
            return None, "Unauthorized"

        try:
            ticket_type = TicketType(
                event_id=event.id,
                name=data["name"],
                description=data.get("description"),
                price=data.get("price", 0),
                capacity=data.get("capacity"),
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
    def get_attendee_dashboard_data(cls, user_id: int) -> Dict:
        """
        Gathers data for the attendee dashboard.
        """
        all_registrations = EventRegistration.query.filter_by(user_id=user_id).all()

        upcoming_registrations = []
        past_registrations = []
        attended_count = 0
        total_spent = 0.0

        for reg in all_registrations:
            event = Event.query.get(reg.event_id)
            if not event:
                continue

            reg_dict = cls._registration_to_dict(reg)
            reg_dict['event'] = cls._event_to_dict(event)

            if event.end_date and event.end_date >= date.today():
                upcoming_registrations.append(reg_dict)
            else:
                past_registrations.append(reg_dict)

            if reg.status == 'checked_in':
                attended_count += 1
            total_spent += float(reg.registration_fee)

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
    def get_organizer_dashboard_data(cls, user_id: int) -> Dict:
        """
        Gathers data for the organizer dashboard.
        """
        managed_events = cls.get_events_managed_by_user(user_id)

        total_registrations = 0
        total_revenue = 0.0
        total_capacity = 0
        active_events_list = []
        recent_registrations = []

        # Get event models for detailed stats
        event_ids = [e['event_id'] for e in managed_events if e.get('event_id')]

        for event_dict in managed_events:
            event_model = Event.query.get(event_dict['event_id'])
            if not event_model:
                continue

            # Get registration stats
            registrations = EventRegistration.query.filter_by(event_id=event_model.id).all()
            reg_count = len(registrations)
            reg_revenue = sum(float(r.registration_fee) for r in registrations if r.payment_status == 'paid')

            total_registrations += reg_count
            total_revenue += reg_revenue
            if event_model.max_capacity:
                total_capacity += event_model.max_capacity

            event_dict['registration_count'] = reg_count
            event_dict['revenue'] = reg_revenue
            event_dict['capacity_used'] = round(
                (reg_count / event_model.max_capacity * 100) if event_model.max_capacity else 0, 1)

            if event_dict.get('status') == 'active':
                active_events_list.append(event_dict)

            # Get recent registrations for this event (last 3)
            recent = EventRegistration.query.filter_by(event_id=event_model.id) \
                .order_by(EventRegistration.created_at.desc()).limit(3).all()
            for reg in recent:
                recent_registrations.append({
                    'registration_ref': reg.registration_ref,
                    'full_name': reg.full_name,
                    'event_name': event_model.name,
                    'event_slug': event_model.slug,
                    'created_at': reg.created_at.isoformat() if reg.created_at else None,
                    'status': reg.status
                })

        # Calculate attendance rate
        avg_attendance = 0
        if total_capacity > 0:
            avg_attendance = round((total_registrations / total_capacity) * 100)

        # Weekly trend (last 7 days registrations)
        weekly_trend = []
        for i in range(6, -1, -1):
            day = date.today() - timedelta(days=i)
            count = EventRegistration.query.filter(
                func.date(EventRegistration.created_at) == day
            ).filter(EventRegistration.event_id.in_(event_ids) if event_ids else False).count()
            weekly_trend.append({'date': day.strftime('%a'), 'count': count})

        # Upcoming events
        upcoming_events = [
            e for e in managed_events
            if e.get('start_date') and e['start_date'] >= date.today().isoformat()
        ]
        upcoming_events.sort(key=lambda x: x.get('start_date', '9999-12-31'))

        return {
            "stats": {
                "total_events": len(managed_events),
                "total_registrations": total_registrations,
                "total_revenue": f"{total_revenue:.2f}",
                "avg_attendance": avg_attendance,
                "active_events": len(active_events_list)
            },
            "active_events": active_events_list[:5],
            "upcoming_events": upcoming_events[:5],
            "recent_registrations": recent_registrations[:10],
            "weekly_trend": weekly_trend
        }

    @classmethod
    def get_service_provider_dashboard_data(cls, user_id: int) -> Dict:
        """
        Gathers data for the service provider dashboard.
        Uses signals to collect data from other modules without direct imports.
        """
        from flask import current_app

        # Initialize empty data structures
        dashboard_data = {
            "user_properties": [],
            "user_vehicles": [],
            "relevant_events": [],
            "event_assignments": [],
            "property_count": 0,
            "vehicle_count": 0
        }

        # Emit signal to collect service provider data
        try:
            # Use signal_handlers instead of signals
            from app.events.signal_handlers import service_provider_data_requested

            # Create a mutable container to collect responses
            responses = []

            def collect_response(sender, **kwargs):
                responses.append(kwargs)

            # Temporarily connect a collector
            service_provider_data_requested.connect(collect_response, weak=False)

            # Emit the signal
            service_provider_data_requested.send(
                current_app._get_current_object(),
                user_id=user_id,
                dashboard_data=dashboard_data
            )

            # Disconnect the collector
            service_provider_data_requested.disconnect(collect_response)

            # Process responses from other modules
            for response in responses:
                if 'properties' in response:
                    dashboard_data['user_properties'].extend(response['properties'])
                if 'vehicles' in response:
                    dashboard_data['user_vehicles'].extend(response['vehicles'])
                if 'event_assignments' in response:
                    dashboard_data['event_assignments'].extend(response['event_assignments'])

        except Exception as e:
            logger.warning(f"Could not collect service provider data via signals: {e}")

        # Get relevant events based on user's service locations
        service_cities = set()

        # Collect cities from properties
        for prop in dashboard_data['user_properties']:
            if isinstance(prop, dict) and prop.get('city'):
                service_cities.add(prop['city'])
            elif hasattr(prop, 'city') and prop.city:
                service_cities.add(prop.city)

        # Collect cities from vehicles
        for vehicle in dashboard_data['user_vehicles']:
            if isinstance(vehicle, dict) and vehicle.get('current_location'):
                service_cities.add(vehicle['current_location'])
            elif hasattr(vehicle, 'current_location') and vehicle.current_location:
                service_cities.add(vehicle.current_location)

        # Get events in service cities
        if service_cities:
            all_published_events = Event.query.filter(
                Event.status == EventStatus.PUBLISHED,
                Event.city.in_(list(service_cities))
            ).order_by(Event.start_date).limit(5).all()
            dashboard_data['relevant_events'] = [cls._event_to_dict(e) for e in all_published_events]

        # Update counts
        dashboard_data['property_count'] = len(dashboard_data['user_properties'])
        dashboard_data['vehicle_count'] = len(dashboard_data['user_vehicles'])

        return dashboard_data

    @classmethod
    def register_for_event(cls, identifier: str, user_id: int, data: Dict) -> Tuple[
        Optional[Dict], Optional[str], Optional[str]]:
        """
        Register a user for an event with thread-safe capacity check.
        Uses optimistic concurrency control for better performance at scale.
        Returns: (registration_dict, qr_code_base64, error_message)
        """
        # For high-traffic events, use optimistic concurrency control
        # You can configure which method to use based on event size or other factors
        use_optimistic = True  # Set based on configuration or event size

        if use_optimistic:
            return cls.register_for_event_optimistic(identifier, user_id, data)
        else:
            # Fall back to pessimistic locking for smaller events
            return cls._register_for_event_pessimistic(identifier, user_id, data)

    @classmethod
    def _register_for_event_pessimistic(cls, identifier: str, user_id: int, data: Dict) -> Tuple[
        Optional[Dict], Optional[str], Optional[str]]:
        """
        Fallback registration method using pessimistic locking.
        """
        from sqlalchemy import func

        try:
            # Start a transaction
            with db.session.begin_nested():
                # 1. Fetch event with lock
                event = Event.query.with_for_update().filter_by(slug=identifier).first()
                if not event:
                    return None, None, "Event not found"

                # 2. Identify the ticket type
                ticket_type_id = data.get("ticket_type_id")
                ticket_type = None

                if ticket_type_id:
                    # Lock specific ticket type row
                    ticket_type = TicketType.query.with_for_update().filter_by(
                        id=ticket_type_id,
                        event_id=event.id
                    ).first()
                    if not ticket_type:
                        return None, None, "Invalid ticket type"
                else:
                    # Get first active ticket type with lock
                    ticket_type = TicketType.query.with_for_update().filter_by(
                        event_id=event.id,
                        is_active=True
                    ).order_by(TicketType.price.asc()).first()
                    if not ticket_type:
                        return None, None, "No active ticket types available for this event."

                # 3. Perform atomic capacity check using available_seats
                if ticket_type.capacity > 0:  # 0 means unlimited
                    # Use available_seats for faster concurrency control
                    if ticket_type.available_seats is None:
                        # Initialize available_seats if not set
                        current_count = db.session.query(func.count(EventRegistration.id)).filter_by(
                            ticket_type_id=ticket_type.id
                        ).scalar()
                        ticket_type.available_seats = max(0, ticket_type.capacity - current_count)

                    if ticket_type.available_seats <= 0:
                        raise SoldOutException(f"Ticket tier '{ticket_type.name}' is sold out")

                    # Reserve a seat
                    ticket_type.available_seats -= 1

                # 4. Check if user already registered
                existing = EventRegistration.query.filter_by(
                    event_id=event.id,
                    user_id=user_id
                ).first()
                if existing:
                    return None, None, "You are already registered for this event"

                # 5. Create registration
                # Get the next sequence number safely using count
                from sqlalchemy import func
                count = db.session.query(func.count(EventRegistration.id)).filter_by(
                    event_id=event.id
                ).scalar()
                sequence = (count if count else 0) + 1

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
                    registration_fee=float(ticket_type.price),
                    payment_status="free" if ticket_type.price == 0 else "pending",
                    registered_by="self",
                    status="confirmed" if ticket_type.price == 0 else "pending_payment"
                )

                registration.generate_refs(event.slug, sequence)
                db.session.add(registration)

                # Flush to get ID but don't commit yet
                db.session.flush()

                # Generate QR code
                qr_code = cls._generate_qr_code(registration.qr_token, registration.registration_ref)

                logger.info(f"User {user_id} registered: {registration.registration_ref}")

                # Send signal for loose coupling
                if SIGNALS_AVAILABLE:
                    try:
                        from flask import current_app
                        # Use signal_handlers instead of signals
                        from app.events.signal_handlers import event_registered, offer_services_after_registration

                        # Emit registration signal
                        event_registered.send(
                            current_app._get_current_object(),
                            user_id=user_id,
                            event_id=event.id,
                            registration_id=registration.id,
                            ticket_type=ticket_type.name
                        )

                        # Emit service offering signal
                        offer_services_after_registration.send(
                            current_app._get_current_object(),
                            user_id=user_id,
                            event_id=event.id,
                            event_slug=event.slug,
                            event_name=event.name,
                            event_city=event.city,
                            event_start_date=event.start_date.isoformat() if event.start_date else None,
                            registration_id=registration.id
                        )
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
        """
        Validate a discount code for an event using the DiscountCode model.

        Returns: (discount_amount, error_message)
        - discount_amount: The amount to subtract from the ticket price
        - error_message: None if valid, otherwise error description
        """
        from decimal import Decimal
        from datetime import datetime

        event = cls.get_event_model(identifier)
        if not event:
            return None, "Event not found"

        # Get ticket type if specified
        ticket_type = None
        if ticket_type_id:
            ticket_type = TicketType.query.filter_by(id=ticket_type_id, event_id=event.id).first()
            if not ticket_type:
                return None, "Invalid ticket type"

        # Look up the code in the database
        from app.events.models import DiscountCode
        discount = DiscountCode.query.filter_by(
            event_id=event.id,
            code=code.strip().upper(),
            is_active=True
        ).first()

        if not discount:
            return None, "Invalid discount code"

        # Check if discount code is valid
        if not discount.is_valid():
            return None, "Discount code has expired or reached its usage limit"

        # Calculate discount amount
        if ticket_type:
            ticket_price = Decimal(str(ticket_type.price))
        else:
            ticket_price = Decimal("0.00")

        discount_amount = discount.calculate_discount(ticket_price)

        # Increment usage count
        discount.used_count = (discount.used_count or 0) + 1
        db.session.add(discount)
        # Don't commit here — let the caller's transaction handle it

        logger.info(
            f"Discount code '{code}' validated for event '{identifier}': "
            f"{discount_amount}"
        )
        return discount_amount, None

    @classmethod
    def create_participation(cls, user_id: int, identifier: str, role: str = 'attendee', 
                           control_mode: str = 'self_managed') -> Tuple[Optional[Dict], Optional[str]]:
        """
        Create a new event participation record.
        Returns: (participation_dict, error_message)
        """
        try:
            from app.events.models import Event, EventParticipation, ParticipationRole, ParticipationControlMode
            
            event = Event.query.filter_by(slug=identifier).first()
            if not event:
                return None, "Event not found"
            
            # Check if participation already exists
            existing = EventParticipation.query.filter_by(
                event_id=event.id,
                user_id=user_id
            ).first()
            
            if existing:
                return cls._participation_to_dict(existing), "Participation already exists"
            
            # Create new participation
            participation = EventParticipation(
                event_id=event.id,
                user_id=user_id,
                role=ParticipationRole(role),
                control_mode=ParticipationControlMode(control_mode),
                status='confirmed'
            )
            
            db.session.add(participation)
            db.session.commit()
            
            # Log audit event
            try:
                from app.audit.comprehensive_audit import AuditService
                AuditService.data_change(
                    entity_type="event_participation",
                    entity_id=str(participation.id),
                    operation="create",
                    old_value=None,
                    new_value={
                        "event_id": event.id,
                        "user_id": user_id,
                        "role": role,
                        "control_mode": control_mode
                    },
                    changed_by=user_id,
                    extra_data={"event_slug": identifier}
                )
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
        """
        Assign a service booking to an attendee for an event.
        booking_type can be: 'accommodation', 'transport', 'meal'
        Returns: (assignment_dict, error_message)
        """
        try:
            from app.events.models import Event, EventAssignment, EventParticipation
            
            event = Event.query.filter_by(slug=identifier).first()
            if not event:
                return None, "Event not found"
            
            # Check if attendee is participating in the event
            participation = EventParticipation.query.filter_by(
                event_id=event.id,
                user_id=attendee_id
            ).first()
            
            if not participation:
                return None, "User is not participating in this event"
            
            # Check for existing assignment
            assignment = EventAssignment.query.filter_by(
                event_id=event.id,
                attendee_id=attendee_id
            ).first()
            
            if not assignment:
                # Create new assignment
                assignment = EventAssignment(
                    event_id=event.id,
                    attendee_id=attendee_id,
                    managed_by=managed_by,
                    notes=notes
                )
                db.session.add(assignment)
            
            # Update the appropriate booking field
            if booking_type == 'accommodation':
                assignment.accommodation_booking_id = booking_id
                # Also update the accommodation booking with event_id
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
                # Also update the transport booking with event_id
                try:
                    # The Booking class is in transport.models
                    from app.transport.models import Booking
                    transport_booking = Booking.query.get(booking_id)
                    if transport_booking:
                        transport_booking.event_id = event.id
                        transport_booking.event_participation_id = participation.id
                except ImportError:
                    logger.warning("Could not import Booking from transport.models, skipping event_id update")
            elif booking_type == 'meal':
                assignment.meal_booking_id = booking_id
                # Meal booking would need its own model
            else:
                return None, f"Invalid booking type: {booking_type}"
            
            db.session.commit()
            
            # Log audit event
            try:
                from app.audit.comprehensive_audit import AuditService
                AuditService.data_change(
                    entity_type="event_assignment",
                    entity_id=str(assignment.id),
                    operation="update",
                    old_value=None,
                    new_value={
                        "event_id": event.id,
                        "attendee_id": attendee_id,
                        f"{booking_type}_booking_id": booking_id,
                        "managed_by": managed_by
                    },
                    changed_by=managed_by or attendee_id,
                    extra_data={"event_slug": identifier, "booking_type": booking_type}
                )
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
        """Convert EventParticipation model to dict"""
        return {
            "id": participation.id,
            "event_id": participation.event_id,
            "user_id": participation.user_id,
            "role": participation.role.value if participation.role else None,
            "control_mode": participation.control_mode.value if participation.control_mode else None,
            "status": participation.status.value if participation.status else None,
            "joined_at": participation.joined_at.isoformat() if participation.joined_at else None,
            "left_at": participation.left_at.isoformat() if participation.left_at else None,
            "notes": participation.notes,
            "metadata": participation.metadata,
            "created_at": participation.created_at.isoformat() if participation.created_at else None,
            "updated_at": participation.updated_at.isoformat() if participation.updated_at else None,
        }

    @classmethod
    def _assignment_to_dict(cls, assignment) -> Dict:
        """Convert EventAssignment model to dict"""
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
            "created_at": assignment.created_at.isoformat() if assignment.created_at else None,
            "updated_at": assignment.updated_at.isoformat() if assignment.updated_at else None,
        }



    @classmethod
    def get_event_participations(cls, identifier: str, role: Optional[str] = None) -> List[Dict]:
        """
        Get all participations for a specific event.
        Returns: list of participation dictionaries
        """
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
        """
        Get all assignments for a specific event.
        Returns: list of assignment dictionaries
        """
        try:
            from app.events.models import Event, EventAssignment
            
            event = Event.query.filter_by(slug=identifier).first()
            if not event:
                return []
            
            assignments = EventAssignment.query.filter_by(
                event_id=event.id
            ).order_by(EventAssignment.created_at.desc()).all()
            
            return [cls._assignment_to_dict(assignment) for assignment in assignments]
            
        except Exception as e:
            logger.error(f"Error getting event assignments: {e}")
            return []

    @classmethod
    def get_attendee_assignments(cls, user_id: int) -> List[Dict]:
        """
        Get all assignments for a specific attendee.
        Returns: list of assignment dictionaries
        """
        try:
            from app.events.models import EventAssignment
            
            assignments = EventAssignment.query.filter_by(
                attendee_id=user_id
            ).order_by(EventAssignment.created_at.desc()).all()
            
            return [cls._assignment_to_dict(assignment) for assignment in assignments]
            
        except Exception as e:
            logger.error(f"Error getting attendee assignments: {e}")
            return []

    @classmethod
    def cancel_registration(cls, registration_ref: str, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Cancel a registration for an event.
        Returns: (success, error_message)
        """
        from datetime import date
        
        registration = EventRegistration.query.filter_by(registration_ref=registration_ref).first()
        if not registration:
            return False, "Registration not found"
        
        if registration.user_id != user_id:
            return False, "Unauthorized"
        
        if registration.status == "cancelled":
            return False, "Already cancelled"
        
        if registration.status == "checked_in":
            return False, "Cannot cancel a checked-in registration"
        
        event = Event.query.get(registration.event_id)
        if event and event.start_date and event.start_date < date.today():
            return False, "Cannot cancel past events"
        
        # Mark as cancelled
        registration.status = "cancelled"
        
        # Release capacity back to ticket type
        if registration.ticket_type_id:
            ticket_type = TicketType.query.get(registration.ticket_type_id)
            if ticket_type and ticket_type.capacity and ticket_type.capacity > 0:
                ticket_type.available_seats = (ticket_type.available_seats or 0) + 1
                ticket_type.version = (ticket_type.version or 0) + 1
        
        db.session.commit()
        logger.info(f"Registration {registration_ref} cancelled by user {user_id}")
        return True, None

    @classmethod
    def sanitize_status(cls, status_value):
        """
        Safely convert any status value to a valid EventStatus enum value.
        Returns EventStatus.DRAFT.value for any unrecognized status.
        This is a legacy data protection layer.
        """
        from app.events.constants import EventStatus
        
        if status_value is None:
            return EventStatus.DRAFT.value
        
        # If it's already an EventStatus enum member
        if isinstance(status_value, EventStatus):
            return status_value.value
        
        # Try to match with EventStatus enum values
        status_str = str(status_value)
        try:
            return EventStatus(status_str).value
        except ValueError:
            # Log unrecognized status for monitoring
            logger.warning(f"Legacy status value encountered: '{status_str}', defaulting to DRAFT")
            return EventStatus.DRAFT.value

    @classmethod
    def get_admin_dashboard_data(cls) -> Dict:
        """Get comprehensive admin dashboard statistics"""
        try:
            # Debug logging
            logger.info("Fetching admin dashboard data")

            from app.events.models import Event, EventRegistration

            # Count events, excluding soft-deleted ones
            total_events = Event.query.filter_by(is_deleted=False).count()
            
            # Use EventStatus enum values for valid statuses
            published_events = Event.query.filter_by(status=EventStatus.PUBLISHED, is_deleted=False).count()
            pending_events = Event.query.filter_by(status=EventStatus.PENDING_APPROVAL, is_deleted=False).count()
            rejected_events = Event.query.filter_by(status=EventStatus.REJECTED, is_deleted=False).count()
            suspended_events = Event.query.filter_by(status=EventStatus.SUSPENDED, is_deleted=False).count()
            archived_events = Event.query.filter_by(status=EventStatus.ARCHIVED, is_deleted=False).count()
            
            # Handle legacy 'deactivated' status separately (not in EventStatus enum)
            deactivated_events = Event.query.filter(
                Event.status == 'deactivated',
                Event.is_deleted == False
            ).count()

            # Count registrations
            total_registrations = EventRegistration.query.count()
            checked_in_registrations = EventRegistration.query.filter_by(status='checked_in').count()

            logger.info(f"Admin dashboard stats: total_events={total_events}, published={published_events}, pending={pending_events}")

            return {
                'total_events': total_events,
                'published_events': published_events,
                'pending_events': pending_events,
                'rejected_events': rejected_events,
                'suspended_events': suspended_events,
                'deactivated_events': deactivated_events,
                'archived_events': archived_events,
                'total_registrations': total_registrations,
                'checked_in_registrations': checked_in_registrations
            }
        except Exception as e:
            logger.error(f"Error in get_admin_dashboard_data: {e}")
            # Return zeros to prevent template errors
            return {
                'total_events': 0,
                'published_events': 0,
                'pending_events': 0,
                'rejected_events': 0,
                'suspended_events': 0,
                'deactivated_events': 0,
                'archived_events': 0,
                'total_registrations': 0,
                'checked_in_registrations': 0
            }
