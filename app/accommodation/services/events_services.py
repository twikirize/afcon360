"""
Event Service - Manage events (AFCON, Crusades, etc.)
"""

from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

from app.extensions import db
from app.accommodation.models.booking import BookingContextType
from app.accommodation.services.booking_service import BookingService
from app.auth.policy import can
from flask_login import current_user

logger = logging.getLogger(__name__)


class EventService:
    """
    Handles event management for the accommodation module.
    Currently uses in-memory storage (dict) for events.
    Designed to be replaced with a proper Event database model in production.
    """

    # ===============================
    # In-memory events (replace with DB later)
    # ===============================
    _events: Dict[str, Dict] = {}

    # -------------------------------
    # CRUD OPERATIONS
    # -------------------------------
    @classmethod
    def get_all_events(cls, status: str = None) -> List[Dict]:
        """Get all events, optionally filtered by status"""
        events = list(cls._events.values())
        if status:
            events = [e for e in events if e.get("status") == status]
        return sorted(events, key=lambda e: e.get("start_date", ""))

    @classmethod
    def get_event(cls, event_id: str) -> Optional[Dict]:
        """Get a single event by ID or slug"""
        return cls._events.get(event_id)

    @classmethod
    def create_event(cls, data: Dict, organizer_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Create a new event"""
        try:
            import re

            slug = data.get("slug") or re.sub(r"[^a-z0-9]+", "-", data["name"].lower()).strip("-")

            # Ensure uniqueness
            if slug in cls._events:
                slug = f"{slug}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            event = {
                "id": slug,
                "slug": slug,
                "name": data["name"],
                "description": data.get("description", ""),
                "city": data["city"],
                "venue": data.get("venue", ""),
                "start_date": data.get("start_date"),
                "end_date": data.get("end_date"),
                "organizer_id": organizer_id,
                "status": "pending",  # needs admin approval
                "created_at": datetime.utcnow().isoformat(),
                "metadata": data.get("metadata", {}),
            }

            cls._events[slug] = event
            logger.info(f"Event created: {slug} by organizer {organizer_id}")
            return event, None

        except Exception as e:
            logger.error(f"Error creating event: {e}")
            return None, str(e)

    @classmethod
    def update_event(cls, event_id: str, data: Dict, user_id: int) -> Tuple[bool, Optional[str]]:
        """Update an event if user has permission"""
        event = cls._events.get(event_id)
        if not event:
            return False, "Event not found"

        # Permission check: organizer or admin
        if event.get("organizer_id") != user_id and not can(current_user, "admin"):
            return False, "Unauthorized to update event"

        import re

        for key, value in data.items():
            if key in ["name", "description", "city", "venue", "start_date", "end_date", "metadata"]:
                if key == "name":
                    new_slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
                    if new_slug != event_id:
                        cls._events[new_slug] = event.copy()
                        cls._events[new_slug]["slug"] = new_slug
                        cls._events[new_slug]["name"] = value
                        del cls._events[event_id]
                        event = cls._events[new_slug]
                        continue
                event[key] = value

        event["updated_at"] = datetime.utcnow().isoformat()
        logger.info(f"Event updated: {event_id}")
        return True, None

    @classmethod
    def delete_event(cls, event_id: str, user_id: int) -> Tuple[bool, Optional[str]]:
        """Delete an event if no bookings exist"""
        event = cls._events.get(event_id)
        if not event:
            return False, "Event not found"

        # Only organizer or admin can delete
        if event.get("organizer_id") != user_id and not can(current_user, "admin"):
            return False, "Unauthorized to delete event"

        bookings = BookingService.get_bookings_by_context(BookingContextType.EVENT.value, context_id=event_id)
        if bookings:
            return False, f"Cannot delete event with {len(bookings)} existing bookings"

        del cls._events[event_id]
        logger.info(f"Event deleted: {event_id}")
        return True, None

    # -------------------------------
    # EVENT APPROVAL WORKFLOW
    # -------------------------------
    @classmethod
    def approve_event(cls, event_id: str, admin_id: int) -> Tuple[bool, Optional[str]]:
        """Admin approves event"""
        event = cls._events.get(event_id)
        if not event:
            return False, "Event not found"

        event["status"] = "active"
        event["approved_at"] = datetime.utcnow().isoformat()
        event["approved_by"] = admin_id
        logger.info(f"Event approved: {event_id} by admin {admin_id}")
        return True, None

    @classmethod
    def reject_event(cls, event_id: str, admin_id: int, reason: str = None) -> Tuple[bool, Optional[str]]:
        """Admin rejects event"""
        event = cls._events.get(event_id)
        if not event:
            return False, "Event not found"

        event["status"] = "rejected"
        event["rejected_at"] = datetime.utcnow().isoformat()
        event["rejected_by"] = admin_id
        event["rejection_reason"] = reason
        logger.info(f"Event rejected: {event_id} by admin {admin_id}")
        return True, None

    # -------------------------------
    # EVENT STATS
    # -------------------------------
    @classmethod
    def get_event_stats(cls, event_id: str) -> Dict:
        """Return bookings, revenue, guests per property"""
        event = cls._events.get(event_id)
        if not event:
            return {}

        bookings = BookingService.get_bookings_by_context(BookingContextType.EVENT.value, context_id=event_id)
        total_bookings = len(bookings)
        total_revenue = sum(b.total_amount for b in bookings)
        total_guests = sum(b.num_guests for b in bookings)

        properties = {}
        for b in bookings:
            pid = b.property_id
            if pid not in properties:
                properties[pid] = {"property_id": pid, "bookings": 0, "revenue": 0, "guests": 0}
            properties[pid]["bookings"] += 1
            properties[pid]["revenue"] += float(b.total_amount)
            properties[pid]["guests"] += b.num_guests

        return {
            "event": event,
            "total_bookings": total_bookings,
            "total_revenue": float(total_revenue),
            "total_guests": total_guests,
            "properties": list(properties.values()),
            "bookings": bookings[:10],  # last 10 bookings
        }

    # -------------------------------
    # ORGANIZER METHODS
    # -------------------------------
    @classmethod
    def get_events_by_organizer(cls, organizer_id: int) -> List[Dict]:
        return [e for e in cls._events.values() if e.get("organizer_id") == organizer_id]