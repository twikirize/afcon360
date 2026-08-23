# app/events/view_models.py
"""
ViewModels for Event module - separates presentation from business logic.

These objects expose only what templates and JSON responses need.
They must not make authorization decisions or mutate event state.

Authority reminder:
    Use canonical ownership helpers such as `can_manage_event()` or
    `can_view_coordination()` for access control.  Do not use this view
    model to infer ownership from `organizer_id`.
"""

from typing import Dict, List, Optional, Any
from decimal import Decimal

from app.events.models import Event, TicketType
from app.events.constants import EventStatus


class EventRegistrationViewModel:
    """
    View model for the public event registration/landing flow.

    Contains presentation-safe event details and normalized ticket types.
    """

    def __init__(self, event: Event, current_user=None):
        self.event = event
        self.user = current_user

        # ── Basic event identity ──────────────────────────────────────────
        self.id = event.id
        self.public_id = event.public_id
        self.slug = event.slug
        self.name = event.name
        self.description = event.description or ''
        self.category = event.category
        self.city = event.city
        self.country = event.country
        self.venue = event.venue or ''
        self.website = event.website

        # ── Dates ──────────────────────────────────────────────────────────
        self.start_date = event.start_date.isoformat() if event.start_date else None
        self.end_date = event.end_date.isoformat() if event.end_date else None

        # ── Status ─────────────────────────────────────────────────────────
        # Normalize to string because the model may return an EventStatus enum
        # member or a raw string depending on how SQLAlchemy loaded the row.
        self.status = getattr(event.status, 'value', event.status)

        # ── Registration fields ────────────────────────────────────────────
        self.currency = event.currency
        self.max_capacity = event.max_capacity or 0
        self.registration_required = bool(event.registration_required)
        self.registration_opens_at = (
            event.registration_opens_at.isoformat()
            if getattr(event, "registration_opens_at", None)
            else None
        )
        self.registration_closes_at = (
            event.registration_closes_at.isoformat()
            if getattr(event, "registration_closes_at", None)
            else None
        )

        # ── Contact info ───────────────────────────────────────────────────
        self.contact_email = event.contact_email
        self.contact_phone = event.contact_phone

        # ── Metadata ───────────────────────────────────────────────────────
        self.metadata = event.event_metadata or {}

        # ── Featured state ─────────────────────────────────────────────────
        self.featured = bool(event.featured)

        # ── Ticket type normalization ─────────────────────────────────────
        self.ticket_types: List[Dict[str, Any]] = []
        self.is_paid_event = False
        self.min_price = Decimal("0.00")

        for tt in event.ticket_types:
            if not tt.is_active:
                continue

            price = tt.price or Decimal("0.00")
            if not isinstance(price, Decimal):
                price = Decimal(str(price))

            ticket_dict = {
                "id": tt.id,
                "name": tt.name,
                "price": float(price),
                "price_decimal": price,
                "capacity": tt.capacity or 0,
                "description": tt.description or '',
                "is_active": bool(tt.is_active),
            }

            self.ticket_types.append(ticket_dict)

            if price > 0:
                self.is_paid_event = True

            if self.min_price == Decimal("0.00") or price < self.min_price:
                self.min_price = price

        # Sort ticket types by price, cheapest first.
        self.ticket_types.sort(key=lambda x: x["price"])

        # ── Derived registration state flags ──────────────────────────────
        self.is_published = self.status == EventStatus.PUBLISHED.value
        self.is_registration_open = self.is_published and not self.is_expired

    @property
    def is_expired(self) -> bool:
        """
        Return True if the event has already ended.

        Date-only events are treated as expired after their end_date has
        passed.  This mirrors EventService.is_event_expired().
        """
        if not self.event.end_date:
            return False

        from datetime import date

        end_date = self.event.end_date
        if hasattr(end_date, "date"):
            end_date = end_date.date()

        return end_date < date.today()

    @property
    def free_ticket_types(self) -> List[Dict[str, Any]]:
        return [t for t in self.ticket_types if t["price"] == 0]

    @property
    def paid_ticket_types(self) -> List[Dict[str, Any]]:
        return [t for t in self.ticket_types if t["price"] > 0]

    def to_dict(self) -> Dict:
        """
        Return a presentation-safe dictionary.

        Delegates to EventService._event_to_dict() to keep the public JSON
        shape consistent with the rest of the Events module.
        """
        from app.events.services import EventService

        data = EventService._event_to_dict(self.event)

        # Add normalized view-model ticket metadata without changing the
        # existing public event shape.
        data["ticket_types"] = self.ticket_types
        data["is_paid_event"] = self.is_paid_event
        data["min_price"] = float(self.min_price)
        data["is_registration_open"] = self.is_registration_open
        data["is_expired"] = self.is_expired

        return data