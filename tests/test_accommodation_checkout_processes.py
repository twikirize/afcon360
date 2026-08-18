"""Regression checks for the group checkout and notification contracts."""

from pathlib import Path

from app.accommodation.services.pricing_service import PricingService
from app.notifications.models import Notification


def test_group_pricing_scales_by_requested_rooms():
    property_obj = type(
        "PropertyStub",
        (),
        {
            "base_price_per_night": 100,
            "cleaning_fee": 20,
            "service_fee_pct": 10,
            "tax_rate_pct": 0,
        },
    )()

    result = PricingService.calculate_total(
        property_obj,
        __import__("datetime").date(2026, 9, 1),
        __import__("datetime").date(2026, 9, 2),
        num_guests=5,
        num_rooms=2,
    )

    assert result["num_rooms"] == 2
    assert result["subtotal"] == 200
    assert result["cleaning_fee"] == 40


def test_notification_constraint_matches_pending_booking_type():
    constraints = [
        constraint.sqltext.text
        for constraint in Notification.__table__.constraints
        if hasattr(constraint, "sqltext")
    ]
    notification_constraint = next(text for text in constraints if "type IN" in text)

    assert "booking_pending" in notification_constraint
    assert "third_party_booking" in notification_constraint


def test_checkout_has_no_per_room_submission_and_uses_group_guest_field():
    template = Path("templates/accommodation/guest/checkout.html").read_text(encoding="utf-8-sig")

    assert 'name="num_guests_group"' in template
    assert 'name="room_number" value=""' in template
    assert 'label class="form-label fw-semibold">Room Number' not in template


def test_checkout_validates_party_size_before_payment():
    template = Path("templates/accommodation/guest/checkout.html").read_text(encoding="utf-8-sig")
    script = Path("static/js/modules/accommodation/checkout.js").read_text(encoding="utf-8-sig")

    assert 'data-validate-party' in template
    assert 'name="room_max_guests"' in template
    assert 'function validatePartySize()' in script
    assert 'guests > rooms * maxGuests' in script


def test_property_date_picker_keeps_dates_in_valid_order():
    template = Path("templates/accommodation/guest/detail.html").read_text(encoding="utf-8-sig")
    script = Path("static/js/modules/accommodation/detail.js").read_text(encoding="utf-8-sig")

    assert '<script type="application/ld+json" nonce="{{ csp_nonce }}">' in template
    assert 'id="availability-form"' in template
    assert 'data-property-id="{{ property.id }}"' in template
    assert 'id="booking-form"' in template
    assert "onclick=" not in template
    assert "checkLiveAvailability" not in template
    assert "checkOutInput.disabled = false" in script
    assert "checkOutInput.value = ''" in script
    assert "new URLSearchParams" in script


def test_availability_endpoint_parses_dates_before_service_lookup(app, monkeypatch):
    from datetime import date

    from app.accommodation.services.availability_service import AvailabilityService

    received = {}

    def fake_get_availability_cascade(**kwargs):
        received.update(kwargs)
        return {"room_types": []}

    monkeypatch.setattr(
        AvailabilityService,
        "get_availability_cascade",
        staticmethod(fake_get_availability_cascade),
    )

    with app.test_request_context(
        "/accommodation/api/availability"
        "?property_id=2&check_in=2026-08-20&check_out=2026-08-21"
        "&num_guests=2&num_rooms=1"
    ):
        response = app.view_functions["accommodation.api_availability"]()

    assert response[1] == 200
    assert received["check_in"] == date(2026, 8, 20)
    assert received["check_out"] == date(2026, 8, 21)


def test_confirmation_page_exposes_booking_management_and_payment_reference():
    template = Path("templates/accommodation/guest/confirmation.html").read_text(encoding="utf-8-sig")
    routes = Path("app/accommodation/routes.py").read_text(encoding="utf-8-sig")

    assert "accommodation.guest_amend_booking" in template
    assert "accommodation.guest_cancel_booking" in template
    assert "payment_event.payment_reference" in template
    assert 'name="return_to_confirmation" value="1"' in template
    assert "onclick=" not in template
    assert "payment_event = BookingService.get_payment_event(booking.id)" in routes
    assert "return_to_confirmation" in routes


def test_cancelled_booking_is_presented_as_cancelled_not_confirmed():
    template = Path("templates/accommodation/guest/confirmation.html").read_text(encoding="utf-8-sig")

    assert "Booking Cancelled" in template
    assert "booking.status not in ['cancelled', 'refunded']" in template


def test_my_bookings_renders_string_backed_booking_statuses():
    template = Path("templates/accommodation/guest/my_bookings.html").read_text(encoding="utf-8-sig")

    assert "booking.status.value" not in template
    assert "booking.status|replace('_', ' ')|title" in template


def test_guest_dashboard_separates_cancelled_history_and_uses_csp_safe_forms():
    content = Path("templates/accommodation/guest/_dashboard_content.html").read_text(encoding="utf-8-sig")
    dashboard = Path("templates/accommodation/guest/dashboard.html").read_text(encoding="utf-8-sig")

    assert "cancelled_bookings" in content
    assert "completed_history" in content
    assert 'data-confirm="Cancel this booking?"' in content
    assert "onclick=" not in content
    assert "confirmation.js" in dashboard