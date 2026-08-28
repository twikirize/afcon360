"""Events-owned orchestration that bridges an event assignment to accommodation.

This module deliberately knows only the Accommodation *contract* surface
(AccommodationCoordinationContract). It never imports accommodation models or
writes accommodation tables directly, preserving module independence: Events
asks, Accommodation decides and owns the write.

It is called after a successful accommodation assignment so the attendee
appears in the booking's guest list immediately, and receives an account-free
link to complete missing details.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, url_for

from app.extensions import db


def _link_expiry(event, booking):
    """Expiry = 7 days after the latest of event end or booking check-out."""
    candidates = []
    for value in (getattr(event, "end_date", None), getattr(booking, "check_out", None)):
        if isinstance(value, datetime):
            candidates.append(value)
    base = max(candidates) if candidates else datetime.now(timezone.utc)
    return base + timedelta(days=7)


def _token_for_booking(assignment, booking_reference):
    """Events-owned secret: generate once per assignment, persist on the event
    assignment record so it can be re-sent without re-deriving the token."""
    schedule = dict(assignment.schedule_json or {})
    token = schedule.get("acc_link_token")
    if not token:
        token = secrets.token_urlsafe(32)
        schedule["acc_link_token"] = token
        assignment.schedule_json = schedule
        db.session.flush()
    return token


def issue_accommodation_for_assignment(event, registration, booking, assignment):
    """Bridge entry point: copy attendee details into the booking's guest list
    and email an account-free completion link.

    Non-fatal: email delivery failures are logged and do not fail the assignment.
    """
    from app.accommodation.services.coordination_contract import (
        AccommodationCoordinationContract,
    )

    # 1. Pre-fill a guest slot in the booking from the event attendee.
    AccommodationCoordinationContract.ensure_event_guest_slot(
        booking.booking_reference,
        full_name=registration.full_name,
        email=registration.email,
        phone=getattr(registration, "phone", None),
        nationality=getattr(registration, "nationality", None),
        user_id=registration.user_id,
        event_assignment_id=assignment.id,
    )

    # 2. Generate a per-assignment token and store its hash and expiry on the assignment.
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    assignment.acc_link_token_hash = token_hash
    assignment.acc_link_expires_at = _link_expiry(event, booking)
    # Commit is handled by the outer transaction (GuestCoordinationService).
    # The bridge no longer commits independently to keep the assignment and
    # guest-slot creation atomic.

    # 3. Email the attendee an account-free completion link (best-effort).
    _email_invite(event, registration, booking, token)


def _email_invite(event, registration, booking, token):
    email = (registration.email or "").strip()
    if not email:
        return
    try:
        from app.auth.email_validation import validate_email_address
        if not validate_email_address(email).is_valid:
            current_app.logger.info("Skipping accommodation invite: invalid email %r", email)
            return
    except Exception:
        pass

    try:
        from app.notifications.models import NotificationModule, NotificationType
        from app.notifications.services import NotificationService

        link = url_for("accommodation.assignment_completion", token=token, _external=True)

        # Compute duration in nights
        duration_nights = None
        if booking.check_in and booking.check_out:
            duration_nights = (booking.check_out - booking.check_in).days

        prop = getattr(booking, "accommodation_property", None)
        NotificationService.send(
            user_id=getattr(registration, "user_id", None),
            notification_type=NotificationType.EVENT_ACCOMMODATION_ASSIGNED,
            title="Complete your accommodation details",
            message=(
                f"You have been assigned accommodation for "
                f"{getattr(event, 'name', 'the event')}. "
                "Please complete your guest registration using the link below."
            ),
            email=email,
            channels=["email"],
            link=link,
            module=NotificationModule.ACCOMMODATION,
            force_external=True,
            context={
                "event_name": getattr(event, "name", None),
                "event_slug": getattr(event, "slug", None),
                "registration_ref": getattr(registration, "registration_ref", None),
                "property_title": getattr(prop, "title", None),
                "property_city": getattr(prop, "city", None),
                "property_country": getattr(prop, "country", None),
                "check_in": booking.check_in.isoformat() if booking.check_in else None,
                "check_out": booking.check_out.isoformat() if booking.check_out else None,
                "duration_nights": duration_nights,
                "booking_reference": booking.booking_reference,
                "guest_name": registration.full_name,
            },
        )
    except Exception:
        current_app.logger.exception("Failed to send accommodation invite to %r", email)
