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
    def generate_key(user_id: int, event_slug: str, data_hash: str) -> str:
        """Generate idempotency key from request parameters."""
        import hashlib
        key_data = f"{user_id}:{event_slug}:{data_hash}"
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
            query = query.filter_by(status=status)
        events = query.order_by(Event.start_date).all()
        return [cls._event_to_dict(event) for event in events]

    @classmethod
    def get_event(cls, event_id: str) -> Optional[Dict]:
        """Get a single event by slug"""
        event = Event.query.filter_by(slug=event_id).first()
        return cls._event_to_dict(event) if event else None

    @classmethod
    def create_event(cls, data: Dict, organizer_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Create a new event"""
        try:
            # Generate slug from name
            slug = re.sub(r"[^a-z0-9]+", "-", data["name"].lower()).strip("-")

            # Ensure uniqueness
            original_slug = slug
            counter = 1
            while Event.query.filter_by(slug=slug).first():
                slug = f"{original_slug}-{counter}"
                counter += 1

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
                elif event_type == "paid" and data.get("ticket_tiers"):
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
                    return None, "Invalid ticket configuration for paid event."

            db.session.commit()

            logger.info(f"Event created: {event.slug}")
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
        event.status = "archived"

        db.session.commit()
        return True, None

    @classmethod
    def get_events_by_organizer(cls, organizer_id: int) -> List[Dict]:
        """Get events created by a specific organizer"""
        events = Event.query.filter_by(organizer_id=organizer_id).order_by(Event.created_at.desc()).all()
        return [cls._event_to_dict(event) for event in events]

    @classmethod
    def get_featured_event(cls) -> Optional[Dict]:
        """Get the featured event (AFCON priority)"""
        # Try featured flag first
        featured = Event.query.filter_by(featured=True, status="active").first()
        if featured:
            return cls._event_to_dict(featured)

        # Otherwise get next upcoming event
        from datetime import date
        upcoming = Event.query.filter(
            Event.status == "active",
            Event.start_date >= date.today()
        ).order_by(Event.start_date).first()

        return cls._event_to_dict(upcoming) if upcoming else None

    @classmethod
    def get_upcoming_events(cls, limit: int = 3, exclude_featured: bool = False) -> List[Dict]:
        """Get upcoming events"""
        from datetime import date
        query = Event.query.filter(
            Event.status == "active",
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

        event.status = "active"
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

        event.status = "rejected"
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
        return {
            # Core fields
            "id": event.slug,
            "event_id": event.id,
            "event_ref": event.event_ref,
            "slug": event.slug,
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

            # Status
            "status": event.status,
            "featured": event.featured,

            # Ownership
            "organizer_id": event.organizer_id,

            # Contact & Media
            "website": event.website,
            "contact_email": event.contact_email,
            "contact_phone": event.contact_phone,
            "metadata": event.event_metadata or {},

            # Approval Workflow Fields
            "approved_at": event.approved_at.isoformat() if event.approved_at else None,
            "approved_by_id": event.approved_by_id,
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
    def register_for_event_optimistic(cls, event_slug: str, user_id: int, data: Dict,
                                     idempotency_key: str = None, max_retries: int = 3) -> Tuple[
        Optional[Dict], Optional[str], Optional[str]]:
        """
        Register a user for an event with optimistic concurrency control.
        Better for high-traffic scenarios like AFCON.
        Returns: (registration_dict, qr_code_base64, error_message)
        """
        from sqlalchemy import func, and_

        # Check idempotency
        if idempotency_key:
            if IdempotencyChecker.check_and_store(idempotency_key):
                logger.warning(f"Duplicate registration attempt detected: {idempotency_key}")
                # Try to find existing registration
                # First get the event to get its ID
                event = Event.query.filter_by(slug=event_slug).first()
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
            idempotency_key = IdempotencyChecker.generate_key(user_id, event_slug, data_hash)

        for attempt in range(max_retries):
            try:
                    # 1. Fetch event (no lock needed for optimistic approach)
                    event = Event.query.filter_by(slug=event_slug).first()
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

                    # 3. Handle capacity with atomic SQL update
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
                    # Get the next sequence number safely
                    from sqlalchemy import func
                    max_id = db.session.query(func.max(EventRegistration.id)).filter_by(
                        event_id=event.id
                    ).scalar()
                    sequence = (max_id if max_id else 0) + 1

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
    def add_to_waitlist(cls, event_slug: str, user_id: int, data: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Add user to waitlist when event is sold out.
        Returns: (waitlist_entry_dict, error_message)
        """
        try:
            event = Event.query.filter_by(slug=event_slug, is_deleted=False).first()
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

            logger.info(f"User {user_id} added to waitlist for event {event_slug} at position {waitlist_entry.position}")

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
    def register_for_event_with_payment(cls, event_slug: str, user_id: int, data: Dict) -> Tuple[
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
                event = Event.query.with_for_update().filter_by(slug=event_slug).first()
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
                                reference=f"EVT-REG-{event_slug}-{user_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                                description=f"Registration for {event.name}",
                                metadata={"event_slug": event_slug, "event_name": event.name}
                            )
                        else:
                            # Try to instantiate
                            wallet_service = WalletService()
                            success, result, error = wallet_service.debit(
                                user_id=user_id,
                                amount=Decimal(str(fee)),
                                currency=event.currency,
                                reference=f"EVT-REG-{event_slug}-{user_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                                description=f"Registration for {event.name}",
                                metadata={"event_slug": event_slug, "event_name": event.name}
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

                logger.info(f"User {user_id} registered for {event_slug} with payment {payment_status}")

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
        from datetime import datetime

        registration = EventRegistration.query.filter_by(qr_token=qr_token).first()

        if not registration:
            return False, "Invalid QR code", None

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
            "event_name": event.name if event else "Unknown",
            "registration_ref": registration.registration_ref
        }

        logger.info(f"Checked in: {registration.registration_ref} by user {checked_by_user_id}")

        return True, f"Welcome {registration.full_name}! Successfully checked in.", result

    @classmethod
    def _generate_qr_code(cls, qr_token: str, registration_ref: str) -> str:
        """Generate QR code as base64 string"""
        # Create QR code data (URL to check-in endpoint)
        # For production, use absolute URL
        checkin_url = f"/events/api/checkin?token={qr_token}"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(checkin_url)
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

        return {
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
            "event": {
                "slug": event.slug if event else None,
                "name": event.name if event else None,
                "start_date": event.start_date.isoformat() if event and event.start_date else None,
                "end_date": event.end_date.isoformat() if event and event.end_date else None,
            } if event else None,
        }

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
    def add_ticket_type(cls, event_slug: str, data: Dict, user_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Add a new ticket type to an event"""
        event = cls.get_event_model(event_slug)
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
            all_active_events = Event.query.filter(
                Event.status == 'active',
                Event.city.in_(list(service_cities))
            ).order_by(Event.start_date).limit(5).all()
            dashboard_data['relevant_events'] = [cls._event_to_dict(e) for e in all_active_events]

        # Update counts
        dashboard_data['property_count'] = len(dashboard_data['user_properties'])
        dashboard_data['vehicle_count'] = len(dashboard_data['user_vehicles'])

        return dashboard_data

    @classmethod
    def register_for_event(cls, event_slug: str, user_id: int, data: Dict) -> Tuple[
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
            return cls.register_for_event_optimistic(event_slug, user_id, data)
        else:
            # Fall back to pessimistic locking for smaller events
            return cls._register_for_event_pessimistic(event_slug, user_id, data)

    @classmethod
    def _register_for_event_pessimistic(cls, event_slug: str, user_id: int, data: Dict) -> Tuple[
        Optional[Dict], Optional[str], Optional[str]]:
        """
        Fallback registration method using pessimistic locking.
        """
        from sqlalchemy import func

        try:
            # Start a transaction
            with db.session.begin_nested():
                # 1. Fetch event with lock
                event = Event.query.with_for_update().filter_by(slug=event_slug).first()
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
    def get_admin_dashboard_data(cls) -> Dict:
        """
        Gathers data for the super admin dashboard.
        """
        total_events = Event.query.count()
        active_events = Event.query.filter_by(status='active').count()
        pending_events = Event.query.filter_by(status='pending').count()
        rejected_events = Event.query.filter_by(status='rejected').count()
        total_registrations = EventRegistration.query.count()
        checked_in_registrations = EventRegistration.query.filter_by(status='checked_in').count()

        return {
            'total_events': total_events,
            'active_events': active_events,
            'pending_events': pending_events,
            'rejected_events': rejected_events,
            'total_registrations': total_registrations,
            'checked_in_registrations': checked_in_registrations
        }
