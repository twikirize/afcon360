"""Focused tests for Addendum 2 registration slot behavior."""

from io import BytesIO
from types import SimpleNamespace

from werkzeug.datastructures import FileStorage

from app.accommodation.models.guest_registration import GuestRegistration
from app.accommodation.services.bulk_registration_service import BulkRegistrationService
from app.accommodation.services.registration_permission_service import RegistrationPermissionService


def test_csv_parser_requires_expected_columns():
    upload = FileStorage(
        stream=BytesIO(b"name,email,phone,id_document_type,id_document_number\nA,a@b.test,+256,passport,P1\n"),
        filename="guests.csv",
    )
    assert BulkRegistrationService.parse(upload)[0]["name"] == "A"


def test_removed_registration_keeps_audit_metadata():
    row = GuestRegistration(guest_name="A", booking_id=1, relationship_type="adult")
    row.remove(42, "Seat reassigned")
    assert row.is_active is False
    assert row.removed_by_user_id == 42
    assert row.removed_reason == "Seat reassigned"


def test_booking_owner_can_manage_registrations():
    user = SimpleNamespace(id=7, is_authenticated=True, has_global_role=lambda *_: False)
    booking = SimpleNamespace(booked_by_user_id=7, booking_owner_id=None, host_user_id=None)
    assert RegistrationPermissionService.can_manage_registrations(user, booking)