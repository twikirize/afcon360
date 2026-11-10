"""Bearer-native event discovery and free-ticket registration.

Event publication, registration windows, ticket inventory, registration
records and QR generation remain owned by the existing events domain.
Paid ticket checkout is intentionally gated until the event payment flow has
an approved PIN-authorized, balanced settlement contract.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import or_

from flask import current_app
from app.extensions import db


class NativeEventError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NativeEventService:
    TICKET_TOKEN_MAX_AGE_SECONDS = 900

    @staticmethod
    def _serializer():
        secret = current_app.secret_key
        if not secret:
            raise NativeEventError("events_unavailable", "AFCON360 cannot securely prepare tickets right now.", 503)
        return URLSafeTimedSerializer(secret, salt="afcon360-native-event-ticket-v1")

    @classmethod
    def _get_public_event(cls, public_id):
        from app.events.models import Event
        from app.events.constants import EventStatus

        event = Event.query.filter_by(
            public_id=str(public_id),
            status=EventStatus.PUBLISHED.value,
            is_deleted=False,
        ).first()
        if event is None:
            raise NativeEventError("event_not_found", "This event is not available for public discovery.", 404)
        return event

    @staticmethod
    def _event_summary(event):
        return {
            "public_id": str(event.public_id),
            "slug": event.slug,
            "name": event.name,
            "description": event.description or "",
            "category": event.category,
            "city": event.city,
            "country": event.country,
            "venue": event.venue,
            "start_date": event.start_date.isoformat() if event.start_date else None,
            "end_date": event.end_date.isoformat() if event.end_date else None,
            "currency": str(event.currency or "USD").upper(),
            "featured": bool(event.featured),
            "registration_required": bool(event.registration_required),
            "registration_fee": str(event.registration_fee or Decimal("0")),
            "website": event.website,
        }

    @staticmethod
    def _ticket_token(event, ticket):
        return NativeEventService._serializer().dumps({
            "event_public_id": str(event.public_id),
            "ticket_type_id": int(ticket.id),
            "event_status": str(event.status),
        })

    @classmethod
    def _ticket_types(cls, event):
        from app.events.services import EventService

        availability = EventService.get_registration_availability(event, use_cache=False)
        availability_by_id = {
            int(item["id"]): item
            for item in availability.get("ticket_types", [])
        }
        now = datetime.now(timezone.utc)
        result = []
        for ticket in (event.ticket_types or []):
            if not ticket.is_active:
                continue
            gate = availability_by_id.get(int(ticket.id), {})
            # The atomic inventory service reserves seats by decrementing this
            # database counter; use it rather than a registration-count estimate,
            # which does not include active ticket holds.
            remaining = ticket.available_seats if ticket.capacity and ticket.capacity > 0 else None
            if ticket.capacity and ticket.capacity > 0 and remaining is None:
                ticket._sync_available_seats()
                remaining = ticket.available_seats
            opens_at = ticket.available_from
            closes_at = ticket.available_until
            if opens_at and opens_at.tzinfo is None:
                opens_at = opens_at.replace(tzinfo=timezone.utc)
            if closes_at and closes_at.tzinfo is None:
                closes_at = closes_at.replace(tzinfo=timezone.utc)
            window_open = (not opens_at or now >= opens_at) and (not closes_at or now < closes_at)
            available = (
                availability.get("state") == "open"
                and window_open
                and (remaining is None or int(remaining or 0) > 0)
                and bool(gate.get("is_available_now", True))
            )
            result.append({
                "ticket_token": cls._ticket_token(event, ticket),
                "name": ticket.name,
                "description": ticket.description or "",
                "price": str(ticket.price or Decimal("0")),
                "currency": str(event.currency or "USD").upper(),
                "capacity_limited": bool(ticket.capacity and ticket.capacity > 0),
                "remaining": int(remaining) if remaining is not None else None,
                "available_from": opens_at.isoformat() if opens_at else None,
                "available_until": closes_at.isoformat() if closes_at else None,
                "is_available_now": available,
            })
        return result

    @classmethod
    def list_events(cls, *, query=None, city=None, country=None, category=None, limit=20, offset=0):
        from app.events.models import Event
        from app.events.constants import EventStatus

        limit = max(1, min(int(limit or 20), 50))
        offset = max(0, int(offset or 0))
        q = Event.query.filter(
            Event.status == EventStatus.PUBLISHED.value,
            Event.is_deleted.is_(False),
        )
        if query:
            term = f"%{str(query).strip()[:100]}%"
            q = q.filter(or_(
                Event.name.ilike(term),
                Event.description.ilike(term),
                Event.city.ilike(term),
                Event.venue.ilike(term),
            ))
        if city:
            q = q.filter(Event.city.ilike(f"%{str(city).strip()[:100]}%"))
        if country:
            q = q.filter(Event.country.ilike(f"%{str(country).strip()[:100]}%"))
        if category:
            q = q.filter(Event.category.ilike(f"%{str(category).strip()[:50]}%"))
        q = q.order_by(Event.start_date.asc().nullslast(), Event.created_at.desc(), Event.id.desc())
        items = q.offset(offset).limit(limit + 1).all()
        has_more = len(items) > limit
        items = items[:limit]
        return {
            "items": [cls._event_summary(item) for item in items],
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
        }

    @classmethod
    def get_event(cls, public_id):
        event = cls._get_public_event(public_id)
        data = cls._event_summary(event)
        data["ticket_availability"] = cls._ticket_types(event)
        from app.events.services import EventService
        snapshot = EventService.get_registration_availability(event, use_cache=False)
        data["registration"] = {
            "state": snapshot.get("state"),
            "message": snapshot.get("message"),
            "opens_at": snapshot.get("opens_at"),
            "closes_at": snapshot.get("closes_at"),
            "remaining_capacity": snapshot.get("remaining_capacity"),
        }
        return data

    @classmethod
    def _load_ticket_token(cls, event, token):
        try:
            data = cls._serializer().loads(
                str(token or ""),
                max_age=cls.TICKET_TOKEN_MAX_AGE_SECONDS,
            )
        except SignatureExpired as exc:
            raise NativeEventError("ticket_selection_expired", "The ticket selection expired. Reload the event and try again.", 409) from exc
        except BadSignature as exc:
            raise NativeEventError("ticket_selection_invalid", "This ticket selection is invalid.", 400) from exc
        if data.get("event_public_id") != str(event.public_id):
            raise NativeEventError("ticket_selection_event_mismatch", "This ticket selection belongs to another event.", 403)
        from app.events.models import TicketType
        ticket = TicketType.query.filter_by(
            id=data.get("ticket_type_id"),
            event_id=event.id,
            is_active=True,
        ).first()
        if ticket is None:
            raise NativeEventError("ticket_type_unavailable", "This ticket type is no longer available.", 409)
        return ticket

    @classmethod
    def register_free_ticket(cls, user, *, event_public_id, ticket_token):
        event = cls._get_public_event(event_public_id)
        ticket = cls._load_ticket_token(event, ticket_token)

        from app.events.services import EventService
        gate_error = EventService._registration_gate_error(event, ticket.id)
        if gate_error:
            raise NativeEventError("registration_closed", gate_error, 409)

        price = Decimal(str(ticket.price or "0"))
        if price > Decimal("0"):
            raise NativeEventError(
                "paid_ticket_checkout_unavailable",
                "This ticket requires payment. Native paid-ticket checkout is being completed; no Wallet debit has been made.",
                409,
            )

        from app.events.payment_service import EventPaymentService
        result = EventPaymentService().process_ticket_purchase(
            user_id=int(user.id),
            event_id=int(event.id),
            ticket_type_id=int(ticket.id),
            quantity=1,
            payment_method="wallet",
            create_primary_for_payer=True,
        )
        if not result.get("success"):
            message = str(result.get("error") or "AFCON360 could not complete this registration.")
            code = "already_registered" if "already registered" in message.lower() else "ticket_registration_failed"
            raise NativeEventError(code, message, 409)

        registrations = result.get("registrations") or []
        if len(registrations) != 1 or not registrations[0].get("registration_ref"):
            current_app.logger.error("Event registration service returned an unexpected free-ticket result for user %s", user.public_id)
            raise NativeEventError("ticket_registration_unverified", "AFCON360 could not verify the ticket registration. Contact support before trying again.", 503)

        from app.events.models import EventRegistration
        registration = EventRegistration.query.filter_by(
            registration_ref=registrations[0]["registration_ref"],
            event_id=event.id,
            booked_by_user_id=user.id,
        ).first()
        if registration is None:
            raise NativeEventError("ticket_registration_unverified", "The registration was created but could not be verified for this account. Contact support.", 503)
        return cls._serialize_registration(registration)

    @staticmethod
    def _serialize_registration(registration):
        from app.events.services import EventService
        event = db.session.get(EventService._get_event_model_class(), registration.event_id)
        return {
            "registration_reference": registration.registration_ref,
            "ticket_number": registration.ticket_number,
            "qr_code": EventService._generate_qr_code(registration.qr_token, registration.registration_ref),
            "event": {
                "public_id": str(event.public_id) if event else None,
                "name": event.name if event else None,
                "city": event.city if event else None,
                "country": event.country if event else None,
                "start_date": event.start_date.isoformat() if event and event.start_date else None,
                "end_date": event.end_date.isoformat() if event and event.end_date else None,
            },
            "ticket_type": registration.ticket_type,
            "attendee_name": registration.full_name,
            "status": registration.status,
            "payment_status": registration.payment_status,
            "amount": str(registration.registration_fee or Decimal("0")),
            "currency": str(event.currency if event else "USD").upper(),
            "created_at": registration.created_at.isoformat() if registration.created_at else None,
        }

    @classmethod
    def list_registrations(cls, user, *, limit=20, offset=0):
        from app.events.models import EventRegistration
        limit = max(1, min(int(limit or 20), 50))
        offset = max(0, int(offset or 0))
        q = EventRegistration.query.filter(or_(
            EventRegistration.user_id == int(user.id),
            EventRegistration.booked_by_user_id == int(user.id),
            EventRegistration.attendee_user_id == int(user.id),
        ))
        rows = q.order_by(EventRegistration.created_at.desc()).offset(offset).limit(limit).all()
        return {
            "items": [cls._serialize_registration(item) for item in rows],
            "limit": limit,
            "offset": offset,
        }

    @classmethod
    def get_registration(cls, user, registration_reference):
        from app.events.models import EventRegistration
        registration = EventRegistration.query.filter_by(
            registration_ref=str(registration_reference),
        ).filter(or_(
            EventRegistration.user_id == int(user.id),
            EventRegistration.booked_by_user_id == int(user.id),
            EventRegistration.attendee_user_id == int(user.id),
        )).first()
        if registration is None:
            raise NativeEventError("registration_not_found", "Ticket registration not found.", 404)
        return cls._serialize_registration(registration)
