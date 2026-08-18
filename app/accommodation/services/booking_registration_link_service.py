"""Creation and lookup helpers for shared guest registration links."""

import hashlib
import secrets
from datetime import datetime, timezone

from app import db
from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.models.booking_registration_link import BookingRegistrationLink


class BookingRegistrationLinkService:
    @staticmethod
    def create_for_booking(booking):
        existing = BookingRegistrationLink.query.filter_by(booking_id=booking.id).first()
        if existing:
            return existing, None
        raw_token = secrets.token_urlsafe(32)
        link = BookingRegistrationLink(
            booking_id=booking.id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            max_registrants=max(1, int(booking.num_guests or 1)),
            expires_at=datetime.combine(booking.check_in, datetime.min.time(), tzinfo=timezone.utc)
            if booking.check_in else None,
        )
        db.session.add(link)
        db.session.commit()
        return link, raw_token

    @staticmethod
    def find_by_token(token, *, lock=False):
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        query = BookingRegistrationLink.query.filter_by(
            token_hash=token_hash, is_active=True
        )
        if lock:
            query = query.with_for_update()
        return query.first()