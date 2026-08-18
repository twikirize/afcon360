#app/accommomodation/services/registration_service.py
"""Canonical write path for manual, bulk, placeholder, and replacement rows."""

import uuid

from app import db
from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.models.guest_registration import GuestRegistration


class RegistrationService:
    """Manage active registration slots without deleting historical rows."""

    @staticmethod
    def active_count(booking_id):
        return GuestRegistration.query.filter_by(
            booking_id=booking_id, is_active=True
        ).count()

    @staticmethod
    def create(booking, *, name, email=None, phone=None, id_document_type=None,
               id_document_number=None, source="host", placeholder=False,
               replaces_registration_id=None, import_batch_id=None, status=None):
        name = (name or "").strip()
        if not name:
            raise ValueError("Guest name is required")

        # Lock the booking row for the duration of this check-then-insert.
        # Without this, two near-simultaneous registrations for the last open
        # slot (e.g. two people opening the same shared link at once) can
        # both pass active_count() before either commits, over-filling the
        # booking. This is the same class of race already identified in this
        # codebase's booking-concurrency work — same fix, applied here.
        db.session.query(AccommodationBooking).filter_by(
            id=booking.id
        ).with_for_update().first()

        if RegistrationService.active_count(booking.id) >= int(booking.num_guests or 1):
            raise ValueError("All registration slots are currently filled")

        complete = bool(name and email and phone and id_document_type and id_document_number)
        row = GuestRegistration(
            booking_id=booking.id,
            guest_name=name[:255],
            guest_email=(email or "").strip()[:255] or None,
            guest_phone=(phone or "").strip()[:50] or None,
            id_document_type=(id_document_type or "").strip()[:30] or None,
            id_document_number=(id_document_number or "").strip()[:100] or None,
            relationship_type="adult",
            status=status or ("pending" if placeholder or not complete else "completed"),
            registration_source=source,
            is_placeholder=placeholder,
            replaces_registration_id=replaces_registration_id,
            import_batch_id=import_batch_id,
        )
        db.session.add(row)
        # Commit here (rather than leaving it to the caller) so the row lock
        # taken above is released as soon as this slot is claimed, not held
        # open until whatever the caller does next.
        db.session.commit()
        return row

    @staticmethod
    def remove(row, actor_id, reason):
        if not row.is_active:
            raise ValueError("Registration is already inactive")
        row.remove(actor_id, reason)
        db.session.commit()
        return row

    @staticmethod
    def replace(booking, row, actor_id, reason, **details):
        RegistrationService.remove(row, actor_id, reason)
        return RegistrationService.create(
            booking, source=details.pop("source", "host"),
            replaces_registration_id=row.id, **details
        )

    @staticmethod
    def bulk_create(booking, rows):
        batch_id = uuid.uuid4().hex
        summary = {"batch_id": batch_id, "registered": 0, "incomplete": 0, "failed": []}
        for number, data in enumerate(rows, start=2):
            name = (data.get("name") or "").strip()
            if not name:
                summary["failed"].append({"row": number, "reason": "missing name", "data": data})
                continue
            try:
                row = RegistrationService.create(
                    booking, name=name, email=data.get("email"), phone=data.get("phone"),
                    id_document_type=data.get("id_document_type"),
                    id_document_number=data.get("id_document_number"),
                    source="bulk_upload", import_batch_id=batch_id,
                )
                summary["registered"] += 1
                if row.status == "pending":
                    summary["incomplete"] += 1
            except ValueError as exc:
                summary["failed"].append({"row": number, "reason": str(exc), "data": data})
        return summary