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
from io import BytesIO
import base64
import secrets
from flask import url_for, current_app
from app.extensions import db, redis_client
from app.events.models import Event, TicketType, EventRegistration, EventRole
from app.accommodation.models.booking import AccommodationBooking, BookingContextType
from sqlalchemy import func, case, and_
from decimal import Decimal

# ✅ DEFINE LOGGER FIRST (before any try/except blocks that use it)
logger = logging.getLogger(__name__)

# Conditional imports for service provider data
try:
    from app.accommodation.models.property import Property
except ImportError:
    Property = None
    logger.warning("Accommodation Property model not found. Service Provider dashboard may be limited.")

try:
    from app.transport.models import Vehicle
except ImportError:
    Vehicle = None
    logger.warning("Transport Vehicle model not found. Service Provider dashboard may be limited.")

try:
    from app.wallet.services.wallet_service import WalletService
except ImportError:
    WalletService = None
    logger.warning("WalletService not found. Wallet features may be limited.")



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
        """Delete an event if no bookings exist"""
        event = Event.query.filter_by(slug=event_id).first()
        if not event:
            return False, "Event not found"

        if event.organizer_id != user_id:
            return False, "Unauthorized"

        # Check for existing bookings
        bookings = AccommodationBooking.query.filter_by(
            context_type=BookingContextType.EVENT.value,
            context_id=event.slug
        ).count()

        if bookings > 0:
            return False, f"Cannot delete event with {bookings} existing bookings"

        db.session.delete(event)
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
    def register_for_event(cls, event_slug: str, user_id: int, data: Dict) -> Tuple[
        Optional[Dict], Optional[str], Optional[str]]:
        """
        Register a user for an event with thread-safe capacity check.
        Returns: (registration_dict, qr_code_base64, error_message)
        """
        try:
            # 1. Fetch event first (no lock yet)
            event = cls.get_event_model(event_slug)
            if not event:
                return None, None, "Event not found"

            # 2. Identify the ticket type
            ticket_type_id = data.get("ticket_type_id")
            
            # Start a transaction with explicit locking
            # We use with_for_update() to lock the relevant rows until commit
            
            if ticket_type_id:
                # Lock specific ticket type row
                ticket_type = TicketType.query.with_for_update().get(ticket_type_id)
                if not ticket_type or ticket_type.event_id != event.id:
                    return None, None, "Invalid ticket type"
            else:
                # Fallback to locking the Event row if no specific ticket type
                # (Or pick the first default ticket type and lock it)
                # Re-fetch event with lock if no specific ticket_type_id was provided
                event = Event.query.with_for_update().filter_by(id=event.id).first()
                ticket_type = TicketType.query.with_for_update().filter_by(event_id=event.id, is_active=True).first()
                if not ticket_type:
                    return None, None, "No active ticket types available for this event."


            # 3. Perform atomic capacity check
            if ticket_type and ticket_type.capacity is not None:
                current_count = EventRegistration.query.filter_by(ticket_type_id=ticket_type.id).count()
                if current_count >= ticket_type.capacity:
                    raise SoldOutException(f"Ticket tier '{ticket_type.name}' is sold out")
            elif event.max_capacity is not None:
                # This path is less likely now with ticket types, but kept for robustness
                current_count = EventRegistration.query.filter_by(event_id=event.id).count()
                if current_count >= event.max_capacity:
                    raise SoldOutException("The event has reached full capacity")

            # 4. Check if user already registered (within same lock)
            existing = EventRegistration.query.filter_by(
                event_id=event.id,
                user_id=user_id
            ).first()
            if existing:
                return None, None, "You are already registered for this event"

            # 5. Create registration
            reg_count = EventRegistration.query.filter_by(event_id=event.id).count()
            sequence = reg_count + 1

            registration = EventRegistration(
                event_id=event.id,
                user_id=user_id,
                ticket_type_id=ticket_type.id if ticket_type else None,
                full_name=data.get("full_name"),
                email=data.get("email"),
                phone=data.get("phone"),
                nationality=data.get("nationality"),
                id_number=data.get("id_number"),
                id_type=data.get("id_type", "national_id"),
                ticket_type=ticket_type.name if ticket_type else data.get("ticket_type", "general"),
                registration_fee=float(ticket_type.price) if ticket_type else float(event.registration_fee),
                payment_status="free" if (ticket_type and ticket_type.price == 0) or (not ticket_type and event.registration_fee == 0) else "pending",
                registered_by="self",
            )

            registration.generate_refs(event.slug, sequence)
            db.session.add(registration)
            
            # Commit the transaction (this releases the locks)
            db.session.commit()

            logger.info(f"User {user_id} registered: {registration.registration_ref}")

            return cls._registration_to_dict(registration), None, None # QR code generation moved to async task

        except SoldOutException as e:
            db.session.rollback()
            return None, None, str(e)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration failed: {e}")
            return None, None, "An unexpected error occurred during registration"

    @classmethod
    def register_for_event_with_payment(cls, event_slug: str, user_id: int, data: Dict) -> Tuple[
        Optional[Dict], Optional[str], Optional[str]]:
        """
        Register a user for an event with wallet payment processing.
        Returns: (registration_dict, payment_required, error_message)
        """
        from app.extensions import db
        # from app.wallet.services.wallet_service import WalletService # Moved to top-level import
        from decimal import Decimal

        try:
            event = cls.get_event_model(event_slug)
            if not event:
                return None, None, "Event not found"

            # Get ticket type
            ticket_type_id = data.get("ticket_type_id")
            ticket_type = None
            if ticket_type_id:
                ticket_type = TicketType.query.get(ticket_type_id)
                if not ticket_type or ticket_type.event_id != event.id:
                    return None, None, "Invalid ticket type"
            else:
                # If no specific ticket_type_id is provided, try to find a default/free one
                ticket_type = TicketType.query.filter_by(event_id=event.id, price=0, is_active=True).first()
                if not ticket_type:
                    # Fallback if no free ticket is found and none was selected
                    return None, None, "No ticket type selected or available for registration."


            # Check capacity
            if ticket_type and ticket_type.capacity is not None:
                current_count = EventRegistration.query.filter_by(ticket_type_id=ticket_type.id).count()
                if current_count >= ticket_type.capacity:
                    return None, None, f"Ticket tier '{ticket_type.name}' is sold out"
            elif event.max_capacity is not None: # Fallback to event-level capacity if no ticket type capacity
                current_count = EventRegistration.query.filter_by(event_id=event.id).count()
                if current_count >= event.max_capacity:
                    return None, None, "Event has reached full capacity"

            # Check existing registration
            existing = EventRegistration.query.filter_by(event_id=event.id, user_id=user_id).first()
            if existing:
                return None, None, "You are already registered for this event"

            # Calculate fee
            fee = float(ticket_type.price) if ticket_type else 0.0 # Default to 0 if no ticket type
            requires_payment = fee > 0

            # Process payment if required
            payment_txn_id = None
            if requires_payment:
                if not WalletService:
                    return None, None, "Wallet service not available for payment processing."
                wallet_service = WalletService()
                success, result, error = wallet_service.debit(
                    user_id=user_id,
                    amount=Decimal(str(fee)),
                    currency=event.currency,
                    reference=f"EVT-REG-{event_slug}-{user_id}",
                    description=f"Registration for {event.name}",
                    metadata={"event_slug": event_slug, "event_name": event.name}
                )

                if not success:
                    return None, None, f"Payment failed: {error}"

                payment_txn_id = result.get("transaction_id") if result else None
                payment_status = "paid"
            else:
                payment_status = "free"

            # Create registration
            reg_count = EventRegistration.query.filter_by(event_id=event.id).count()
            sequence = reg_count + 1

            registration = EventRegistration(
                event_id=event.id,
                user_id=user_id,
                ticket_type_id=ticket_type.id if ticket_type else None,
                full_name=data.get("full_name"),
                email=data.get("email"),
                phone=data.get("phone"),
                nationality=data.get("nationality"),
                id_number=data.get("id_number"),
                id_type=data.get("id_type", "national_id"),
                ticket_type=ticket_type.name if ticket_type else data.get("ticket_type", "general"),
                registration_fee=fee,
                payment_status=payment_status,
                wallet_txn_id=payment_txn_id,
                registered_by="self",
                status="confirmed" if payment_status == "paid" or payment_status == "free" else "pending_payment"
            )

            registration.generate_refs(event.slug, sequence)
            db.session.add(registration)
            db.session.commit()

            logger.info(f"User {user_id} registered for {event_slug} with payment {payment_status}")

            # Generate QR code
            qr_code = cls._generate_qr_code(registration.qr_token, registration.registration_ref)

            return cls._registration_to_dict(registration), qr_code, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration with payment failed: {e}")
            return None, None, str(e)

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
        Includes properties, vehicles, and relevant events.
        """
        user_properties = []
        if Property:
            user_properties = Property.query.filter_by(owner_user_id=user_id).all()
        
        user_vehicles = []
        if Vehicle:
            # Assuming Vehicle has an owner_user_id or similar
            user_vehicles = Vehicle.query.filter_by(owner_user_id=user_id).all()

        property_cities = {p.city for p in user_properties if p.city}
        vehicle_cities = {v.current_location for v in user_vehicles if v.current_location} # Assuming current_location for vehicles

        service_cities = property_cities.union(vehicle_cities)

        relevant_events = []
        if service_cities:
            all_active_events = Event.query.filter(
                Event.status == 'active',
                Event.city.in_(list(service_cities))
            ).order_by(Event.start_date).limit(5).all()
            relevant_events = [cls._event_to_dict(e) for e in all_active_events]

        # Placeholder for event-related bookings/assignments for service providers
        event_assignments = [] # e.g., AccommodationBookings linked to events, TransportBookings for events

        return {
            "user_properties": [p.to_dict() for p in user_properties] if Property else [],
            "user_vehicles": [v.to_dict() for v in user_vehicles] if Vehicle else [],
            "relevant_events": relevant_events,
            "event_assignments": event_assignments,
            "property_count": len(user_properties),
            "vehicle_count": len(user_vehicles)
        }

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

