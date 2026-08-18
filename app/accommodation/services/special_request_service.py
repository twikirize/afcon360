"""Single write/read path for booking special requests."""

from datetime import datetime, timezone

from app import db
from app.accommodation.models.special_request import BookingSpecialRequest


class SpecialRequestService:
    """Keep all request channels in one host-facing collection."""

    @staticmethod
    def add_request(
        booking_id,
        request_text,
        *,
        request_type=None,
        guest_registration_id=None,
        requested_by_user_id=None,
        source,
    ):
        text = (request_text or "").strip()
        if not text:
            raise ValueError("Request text is required")
        valid_sources = {"checkout", "confirmation_prompt", "dashboard", "guest_self_registration"}
        if source not in valid_sources:
            raise ValueError("Invalid request source")
        item = BookingSpecialRequest(
            booking_id=booking_id,
            request_text=text,
            request_type=(request_type or "other").strip()[:50],
            guest_registration_id=guest_registration_id,
            requested_by_user_id=requested_by_user_id,
            source=source,
        )
        db.session.add(item)
        db.session.commit()
        return item

    @staticmethod
    def get_for_booking(booking_id):
        return (
            BookingSpecialRequest.query
            .filter_by(booking_id=booking_id)
            .order_by(BookingSpecialRequest.created_at.asc())
            .all()
        )