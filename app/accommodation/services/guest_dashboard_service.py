# app/accommodation/services/guest_dashboard_service.py
"""
Guest Dashboard aggregation service.

Centralises the data the guest-facing dashboard needs: current/upcoming/past
stays, payments due, check-in eligibility, reviewable stays, complaints and
pending amendments. Keeps the route thin and the templates consistent.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_

from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
    AccommodationPaymentStatus,
)
from app.accommodation.models.review import Review
from app.accommodation.state_machine.booking_states import BookingStateMachine


class GuestDashboardService:
    """Encapsulates guest dashboard data aggregation."""

    # Booking statuses that represent an active/future stay for the guest.
    ACTIVE_STATUSES = [
        AccommodationBookingStatus.PENDING_APPROVAL.value,
        AccommodationBookingStatus.CONFIRMED.value,
        AccommodationBookingStatus.CHECKED_IN.value,
    ]

    HISTORY_STATUSES = [
        AccommodationBookingStatus.CHECKED_OUT.value,
        AccommodationBookingStatus.CANCELLED.value,
        AccommodationBookingStatus.REFUNDED.value,
        AccommodationBookingStatus.NO_SHOW.value,
        AccommodationBookingStatus.EXPIRED.value,
        AccommodationBookingStatus.CLOSED.value,
    ]

    @classmethod
    def get_dashboard_data(cls, user_id: int) -> dict:
        """Return aggregated dashboard data for a guest."""
        from app.accommodation.services import search_service
        from app.accommodation.models.feedback import (
            AccommodationComplaint,
            AccommodationBookingAmendment,
        )

        today = date.today()

        # All bookings where the user is the guest, primary guest, or booker.
        bookings = (
            AccommodationBooking.query.filter(
                or_(
                    AccommodationBooking.guest_user_id == user_id,
                    AccommodationBooking.primary_guest_id == user_id,
                    AccommodationBooking.booked_by_user_id == user_id,
                ),
                AccommodationBooking.is_deleted == False,  # noqa: E712
            )
            .order_by(AccommodationBooking.check_in.asc())
            .all()
        )

        enriched = []
        for booking in bookings:
            prop = None
            try:
                prop = search_service.get_property_by_identifier(str(booking.property_id))
            except Exception:
                prop = None
            enriched.append(cls._enrich(booking, prop, today))

        current_stay = next((e for e in enriched if e["is_current"]), None)
        upcoming = [e for e in enriched if e["is_upcoming"]]
        past = [e for e in enriched if e["is_past"]]
        cancelled_bookings = [
            e for e in past
            if e["booking"].status in (
                AccommodationBookingStatus.CANCELLED.value,
                AccommodationBookingStatus.REFUNDED.value,
            )
        ]
        completed_history = [
            e for e in past
            if e["booking"].status not in (
                AccommodationBookingStatus.CANCELLED.value,
                AccommodationBookingStatus.REFUNDED.value,
            )
        ]
        payments_due = [e for e in enriched if e["can_pay"]]
        ready_to_review = [e for e in enriched if e["can_review"]]

        open_complaints = (
            AccommodationComplaint.query.filter_by(user_id=user_id, status="open")
            .filter(AccommodationComplaint.is_deleted == False)  # noqa: E712
            .order_by(AccommodationComplaint.created_at.desc())
            .all()
        )
        all_complaints = (
            AccommodationComplaint.query.filter_by(user_id=user_id)
            .filter(AccommodationComplaint.is_deleted == False)  # noqa: E712
            .order_by(AccommodationComplaint.created_at.desc())
            .all()
        )
        pending_amendments = (
            AccommodationBookingAmendment.query.filter_by(
                requested_by_user_id=user_id, status="pending"
            )
            .filter(AccommodationBookingAmendment.is_deleted == False)  # noqa: E712
            .order_by(AccommodationBookingAmendment.created_at.desc())
            .all()
        )

        stats = {
            "upcoming_count": len(upcoming),
            "current_count": 1 if current_stay else 0,
            "past_count": len(past),
            "payments_due_count": len(payments_due),
            "open_complaints_count": len(open_complaints),
            "pending_amendments_count": len(pending_amendments),
            "reviewable_count": len(ready_to_review),
            "total_due": float(sum(Decimal(str(e["amount_due"])) for e in payments_due)),
        }

        return {
            "today": today,
            "stats": stats,
            "current_stay": current_stay,
            "upcoming": upcoming,
            "past": past,
            "completed_history": completed_history,
            "cancelled_bookings": cancelled_bookings,
            "payments_due": payments_due,
            "ready_to_review": ready_to_review,
            "complaints": all_complaints,
            "open_complaints": open_complaints,
            "pending_amendments": pending_amendments,
        }

    @classmethod
    def _enrich(cls, booking, prop: Optional[dict], today: date) -> dict:
        """Build a render-ready dict for a single booking."""
        status = booking.status

        is_current = status == AccommodationBookingStatus.CHECKED_IN.value
        is_upcoming = (
            status in cls.ACTIVE_STATUSES
            and not is_current
            and (booking.check_out >= today or status == AccommodationBookingStatus.PENDING_APPROVAL.value)
        )
        is_past = (
            status in cls.HISTORY_STATUSES
            or (
                status in cls.ACTIVE_STATUSES
                and not is_current
                and booking.check_out < today
                and status != AccommodationBookingStatus.PENDING_APPROVAL.value
            )
        )

        # Payment due when there is an outstanding amount and the booking is active.
        amount_due = Decimal("0.00")
        try:
            if booking.amount_due is not None:
                amount_due = Decimal(str(booking.amount_due))
            else:
                amount_due = max(
                    Decimal("0.00"),
                    Decimal(str(booking.total_amount or 0)) - Decimal(str(booking.amount_paid or 0)),
                )
        except Exception:
            amount_due = Decimal("0.00")

        payment_active = status in (
            AccommodationBookingStatus.CONFIRMED.value,
            AccommodationBookingStatus.CHECKED_IN.value,
            AccommodationBookingStatus.PENDING_APPROVAL.value,
        )
        can_pay = payment_active and amount_due > Decimal("0.00")

        # Check-in / check-out eligibility via the state machine.
        can_check_in = False
        can_check_out = False
        try:
            if status == AccommodationBookingStatus.CONFIRMED.value:
                can_check_in = BookingStateMachine.can_transition(
                    booking, AccommodationBookingStatus.CHECKED_IN
                )
            if status == AccommodationBookingStatus.CHECKED_IN.value:
                can_check_out = BookingStateMachine.can_transition(
                    booking, AccommodationBookingStatus.CHECKED_OUT
                )
        except Exception:
            can_check_in = False
            can_check_out = False

        # Reviewable after check-out and no existing review.
        can_review = status == AccommodationBookingStatus.CHECKED_OUT.value
        if can_review:
            try:
                if Review.query.filter_by(booking_id=booking.id).first():
                    can_review = False
            except Exception:
                can_review = False

        # Amendable before check-in.
        can_amend = status in (
            AccommodationBookingStatus.CONFIRMED.value,
            AccommodationBookingStatus.PENDING_APPROVAL.value,
        )

        # Cancellable via the booking's own policy.
        can_cancel = False
        try:
            can_cancel, _msg, _refund = booking.can_cancel()
        except Exception:
            can_cancel = False

        # Guest registration requirement (for check-in readiness).
        registration_needed = False
        try:
            regs = list(booking.guest_registrations)
            if regs:
                registration_needed = not all(
                    r.status in ("completed", "skipped") for r in regs
                )
        except Exception:
            registration_needed = False

        property_summary = cls._property_summary(prop, booking)

        return {
            "booking": booking,
            "property": property_summary,
            "status": status,
            "is_current": is_current,
            "is_upcoming": is_upcoming,
            "is_past": is_past,
            "amount_due": float(amount_due),
            "can_pay": can_pay,
            "can_check_in": can_check_in,
            "can_check_out": can_check_out,
            "can_review": can_review,
            "can_amend": can_amend,
            "can_cancel": can_cancel,
            "registration_needed": registration_needed,
            "is_third_party": booking.booking_type == "third_party"
            and booking.booked_by_user_id != booking.guest_user_id,
        }

    @staticmethod
    def _property_summary(prop: Optional[dict], booking) -> dict:
        """Extract a small, template-friendly property snapshot."""
        if prop:
            images = prop.get("images") or []
            return {
                "title": prop.get("title") or prop.get("name") or "Property",
                "images": images,
                "image": images[0] if images else None,
                "address": prop.get("full_address") or prop.get("address"),
                "city": prop.get("city"),
                "cancellation_policy": prop.get("cancellation_policy"),
                "host_name": prop.get("owner_display_name"),
                "host_phone": prop.get("owner_phone"),
                "host_email": prop.get("owner_email"),
            }
        # Fallback to the booking's relationship snapshot.
        p = getattr(booking, "accommodation_property", None)
        if p:
            images = getattr(p, "gallery_images", None) or []
            return {
                "title": getattr(p, "title", "Property"),
                "images": images,
                "image": images[0] if images else None,
                "address": getattr(p, "full_address", None),
                "city": getattr(p, "city", None),
                "cancellation_policy": getattr(p, "cancellation_policy", None),
                "host_name": getattr(p, "owner_display_name", None),
                "host_phone": None,
                "host_email": None,
            }
        return {
            "title": "Property",
            "images": [],
            "image": None,
            "address": None,
            "city": None,
            "cancellation_policy": None,
            "host_name": None,
            "host_phone": None,
            "host_email": None,
        }
