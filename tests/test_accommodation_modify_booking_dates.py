"""
Tests for modify_booking_dates, enhanced check-in / check-out date-adjustment.
Covers: availability failures, past-date rejection, min/max stay, price
delta sign, no-op, no-authorisation, and the PricingService.calculate_modification_price
unit logic.

These are pure unit tests that use stub objects (no DB required), following
the pattern established in test_accommodation_checkout_processes.py.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from app.accommodation.models.booking import AccommodationBookingStatus
from app.accommodation.models.booking_price_adjustment import (
    BookingPriceAdjustment,
    PriceAdjustmentType,
)
from app.accommodation.services.pricing_service import PricingService


# ----------------------------------------------------------------------
# STUBS
# ----------------------------------------------------------------------

def _make_property_stub(
    base_price_per_night=Decimal("100.00"),
    cleaning_fee=Decimal("20.00"),
    service_fee_pct=10,
    tax_rate_pct=0,
    min_stay_nights=None,
    max_stay_nights=None,
):
    return type(
        "PropertyStub",
        (),
        {
            "base_price_per_night": base_price_per_night,
            "cleaning_fee": cleaning_fee,
            "service_fee_pct": service_fee_pct,
            "tax_rate_pct": tax_rate_pct,
            "min_stay_nights": min_stay_nights,
            "max_stay_nights": max_stay_nights,
            "currency": "USD",
        },
    )()


def _make_booking_stub(
    property_obj,
    check_in=None,
    check_out=None,
    nightly_rate=Decimal("100.00"),
    cleaning_fee=Decimal("20.00"),
    service_fee=Decimal("0.00"),
    tax_amount=Decimal("0.00"),
    taxes=Decimal("0.00"),
    total_amount=Decimal("220.00"),
    amount_paid=Decimal("220.00"),
    currency="USD",
    base_total=Decimal("200.00"),
    rooms_requested=1,
    room_type_id=1,
):
    num_nights = (check_out - check_in).days if check_in and check_out else 2
    return type(
        "BookingStub",
        (),
        {
            "property": property_obj,
            "property_id": 1,
            "room_type_id": room_type_id,
            "rooms_requested": rooms_requested,
            "check_in": check_in,
            "check_out": check_out,
            "num_nights": num_nights,
            "nightly_rate": nightly_rate,
            "cleaning_fee": cleaning_fee,
            "service_fee": service_fee,
            "taxes": taxes,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
            "base_total": base_total,
            "amount_paid": amount_paid,
            "amount_due": total_amount - amount_paid,
            "currency": currency,
            "id": 1,
            "host_user_id": 1,
            "is_deleted": False,
            "status": AccommodationBookingStatus.CONFIRMED.value,
            "booking_reference": f"REF-{uuid.uuid4().hex[:8].upper()}",
            "num_nights": num_nights,
            "public_id": "test-public-id",
        },
    )()


def _make_pricing_result():
    return {
        "nights": 2,
        "new_subtotal": Decimal("200.00"),
        "new_total": Decimal("220.00"),
        "old_total": Decimal("220.00"),
        "delta_amount": Decimal("0.00"),
        "refund_amount": Decimal("0.00"),
        "amount_owed": Decimal("0.00"),
        "old_amount_paid": Decimal("220.00"),
        "currency": "USD",
    }


# ----------------------------------------------------------------------
# UNIT: calculate_modification_price
# ----------------------------------------------------------------------

class TestCalculateModificationPrice:
    def _make_booking(self, check_in, check_out, **overrides):
        prop = _make_property_stub()
        defaults = dict(
            property_obj=prop,
            check_in=check_in,
            check_out=check_out,
            nightly_rate=Decimal("100.00"),
            cleaning_fee=Decimal("20.00"),
            service_fee=Decimal("0.00"),
            taxes=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("220.00"),
            amount_paid=Decimal("220.00"),
            base_total=Decimal("200.00"),
        )
        defaults.update(overrides)
        return _make_booking_stub(**defaults)

    def test_shorten_stay_produces_refund(self):
        booking = self._make_booking(
            date.today() + timedelta(days=10),
            date.today() + timedelta(days=12),
        )
        result = PricingService.calculate_modification_price(
            booking, booking.check_in, booking.check_out - timedelta(days=1)
        )
        assert result["old_total"] == Decimal("220.00")
        assert result["delta_amount"] < 0
        assert result["refund_amount"] > 0

    def test_extend_stay_produces_owing(self):
        booking = self._make_booking(
            date.today() + timedelta(days=10),
            date.today() + timedelta(days=12),
        )
        result = PricingService.calculate_modification_price(
            booking, booking.check_in, booking.check_out + timedelta(days=1)
        )
        assert result["new_total"] > result["old_total"]
        assert result["delta_amount"] > 0
        assert result["amount_owed"] > 0

    def test_identical_range_produces_zero_delta(self):
        booking = self._make_booking(
            date.today() + timedelta(days=10),
            date.today() + timedelta(days=12),
        )
        result = PricingService.calculate_modification_price(
            booking, booking.check_in, booking.check_out
        )
        assert result["delta_amount"] == 0
        assert result["refund_amount"] == 0
        assert result["amount_owed"] == 0

    def test_new_check_in_later_reduces_nights(self):
        """Moving check-in forward reduces the stay by one night."""
        booking = self._make_booking(
            date.today() + timedelta(days=10),
            date.today() + timedelta(days=12),
        )
        result = PricingService.calculate_modification_price(
            booking,
            booking.check_in + timedelta(days=1),
            booking.check_out,
        )
        assert result["delta_amount"] < 0
        assert result["refund_amount"] > 0


# ----------------------------------------------------------------------
# UNIT: PriceAdjustmentType enum
# ----------------------------------------------------------------------

class TestPriceAdjustmentType:
    def test_date_modification_value(self):
        assert PriceAdjustmentType.DATE_MODIFICATION.value == "date_modification"

    def test_all_values_are_strings(self):
        for member in PriceAdjustmentType:
            assert isinstance(member.value, str)

    def test_members_exist(self):
        assert hasattr(PriceAdjustmentType, "DATE_MODIFICATION")


# ----------------------------------------------------------------------
# UNIT: modify_booking_dates validation (mocked DB)
# ----------------------------------------------------------------------

class TestModifyBookingDatesValidation:
    """Test validation paths of BookingService.modify_booking_dates
    using mocks so no real DB schema is required."""

    @pytest.fixture
    def mock_booking(self):
        prop = _make_property_stub()
        return _make_booking_stub(
            prop, date.today() + timedelta(days=10), date.today() + timedelta(days=12)
        )

    @pytest.fixture
    def patched_services(self):
        """Yield context managers for patching services at their source modules."""
        patches = [
            patch("app.accommodation.services.availability_service.AvailabilityService"),
            patch("app.accommodation.services.pricing_service.PricingService"),
            patch("app.audit.forensic_audit.ForensicAuditService"),
        ]
        mocks = [p.start() for p in patches]
        yield {
            "avail": mocks[0],
            "pricing": mocks[1],
            "audit": mocks[2],
        }
        for p in patches:
            p.stop()

    @patch("app.accommodation.services.booking_service.db")
    def test_past_check_in_rejected(self, mock_db, mock_booking):
        mock_db.session.execute.return_value.scalar_one.return_value = mock_booking
        mock_db.session.get.side_effect = lambda model, pk: mock_booking.property if model.__name__ == "Property" else mock_booking

        from app.accommodation.services.booking_service import BookingService

        success, error, result = BookingService.modify_booking_dates(
            booking_id=1,
            host_user_id=mock_booking.host_user_id,
            new_check_in=date.today() - timedelta(days=1),
            new_check_out=mock_booking.check_out,
        )

        assert success is False
        assert "past" in error.lower()
        assert result is None

    @patch("app.accommodation.services.booking_service.db")
    def test_no_op_rejected(self, mock_db, mock_booking):
        mock_db.session.execute.return_value.scalar_one.return_value = mock_booking
        mock_db.session.get.side_effect = lambda model, pk: mock_booking.property if model.__name__ == "Property" else mock_booking

        from app.accommodation.services.booking_service import BookingService

        success, error, result = BookingService.modify_booking_dates(
            booking_id=1,
            host_user_id=mock_booking.host_user_id,
            new_check_in=mock_booking.check_in,
            new_check_out=mock_booking.check_out,
        )

        assert success is False
        assert "no date changes" in error.lower()
        assert result is None

    @patch("app.auth.helpers.has_global_role", return_value=False)
    @patch("app.accommodation.services.booking_service.db")
    def test_guest_cannot_authorise(self, mock_db, mock_has_role, mock_booking):
        mock_db.session.execute.return_value.scalar_one.return_value = mock_booking
        mock_db.session.get.side_effect = lambda model, pk: mock_booking.property if model.__name__ == "Property" else mock_booking

        from app.accommodation.services.booking_service import BookingService

        success, error, result = BookingService.modify_booking_dates(
            booking_id=1,
            host_user_id=999,
            new_check_in=mock_booking.check_in,
            new_check_out=mock_booking.check_out + timedelta(days=1),
        )

        assert success is False
        assert "authorised" in error.lower()
        assert result is None

    @patch("app.accommodation.services.availability_service.AvailabilityService")
    @patch("app.accommodation.services.booking_service.db")
    def test_availability_failure_rejected(self, mock_db, mock_avail_service, mock_booking):
        mock_db.session.execute.return_value.scalar_one.return_value = mock_booking
        mock_db.session.get.side_effect = lambda model, pk: mock_booking.property if model.__name__ == "Property" else mock_booking

        mock_avail_service.check_availability_for_dates.return_value = (False, [], "Date range is not available")

        from app.accommodation.services.booking_service import BookingService

        success, error, result = BookingService.modify_booking_dates(
            booking_id=1,
            host_user_id=mock_booking.host_user_id,
            new_check_in=mock_booking.check_in,
            new_check_out=mock_booking.check_out + timedelta(days=1),
        )

        assert success is False
        assert "not available" in error.lower()
        assert result is None

    @patch("app.accommodation.services.booking_service.db")
    def test_checkout_before_checkin_rejected(self, mock_db, mock_booking):
        mock_db.session.execute.return_value.scalar_one.return_value = mock_booking
        mock_db.session.get.side_effect = lambda model, pk: mock_booking.property if model.__name__ == "Property" else mock_booking

        from app.accommodation.services.booking_service import BookingService

        success, error, result = BookingService.modify_booking_dates(
            booking_id=1,
            host_user_id=mock_booking.host_user_id,
            new_check_in=mock_booking.check_in,
            new_check_out=mock_booking.check_in,
        )

        assert success is False
        assert "after" in error.lower()
        assert result is None

    @patch("app.accommodation.services.booking_service.db")
    def test_booking_not_found(self, mock_db):
        mock_db.session.execute.return_value.scalar_one.return_value = None

        from app.accommodation.services.booking_service import BookingService

        success, error, result = BookingService.modify_booking_dates(
            booking_id=999999,
            host_user_id=1,
            new_check_in=date.today() + timedelta(days=5),
            new_check_out=date.today() + timedelta(days=7),
        )

        assert success is False
        assert "not found" in error.lower()
        assert result is None

    @patch("app.accommodation.services.booking_service.db")
    def test_deleted_booking_rejected(self, mock_db, mock_booking):
        mock_booking.is_deleted = True
        mock_db.session.execute.return_value.scalar_one.return_value = mock_booking
        mock_db.session.get.side_effect = lambda model, pk: mock_booking.property if model.__name__ == "Property" else mock_booking

        from app.accommodation.services.booking_service import BookingService

        success, error, result = BookingService.modify_booking_dates(
            booking_id=1,
            host_user_id=mock_booking.host_user_id,
            new_check_in=date.today() + timedelta(days=5),
            new_check_out=date.today() + timedelta(days=7),
        )

        assert success is False
        assert "deleted" in error.lower()
        assert result is None

    @patch("app.accommodation.services.availability_service.AvailabilityService")
    @patch("app.accommodation.services.pricing_service.PricingService")
    @patch("app.audit.forensic_audit.ForensicAuditService")
    @patch("app.notifications.signals.booking_dates_modified")
    @patch("app.accommodation.services.booking_service.db")
    def test_successful_modification_full_flow(
        self, mock_db, mock_signal, mock_audit, mock_pricing, mock_avail, mock_booking
    ):
        """End-to-end mock test: full success path with all services mocked."""
        mock_db.session.execute.return_value.scalar_one.return_value = mock_booking
        mock_db.session.get.side_effect = lambda model, pk: mock_booking.property if model.__name__ == "Property" else mock_booking
        mock_db.session.flush.return_value = None
        mock_db.session.commit.return_value = None

        mock_avail.check_availability_for_dates.return_value = (True, [], None)
        mock_avail.block_room_type_units.return_value = (True, None)
        mock_avail.release_room_type_blocks.return_value = None

        # Make db.session.add + flush simulate ID assignment for BookingPriceAdjustment
        def _add_side_effect(obj):
            if isinstance(obj, BookingPriceAdjustment):
                obj.id = 1
            return None
        mock_db.session.add.side_effect = _add_side_effect
        mock_db.session.flush.return_value = None
        mock_pricing.calculate_modification_price.return_value = {
            "old_total": Decimal("220.00"),
            "new_total": Decimal("110.00"),
            "delta_amount": Decimal("-110.00"),
            "refund_amount": Decimal("110.00"),
            "amount_owed": Decimal("0.00"),
            "old_amount_paid": Decimal("220.00"),
        }
        mock_audit.log_attempt.return_value = 123
        mock_audit.log_completion.return_value = None

        from app.accommodation.services.booking_service import BookingService
        from app.accommodation.models.booking_price_adjustment import PriceAdjustmentType

        success, error, result = BookingService.modify_booking_dates(
            booking_id=1,
            host_user_id=mock_booking.host_user_id,
            new_check_out=mock_booking.check_out - timedelta(days=1),
            reason="Guest requested early departure",
            notify_guest=True,
            ip_address="1.2.3.4",
            user_agent="TestAgent/1.0",
        )

        assert success is True, f"Expected success but got error: {error}"
        assert result is not None
        assert result["adjustment_id"] == 1
        assert str(result["delta_amount"]) == "-110.00"

        # Verify the booking was updated
        assert mock_booking.check_out == date.today() + timedelta(days=11)

        # Verify availability was checked
        mock_avail.check_availability_for_dates.assert_called_once()

        # Verify pricing was called
        mock_pricing.calculate_modification_price.assert_called_once()

        # Verify audit logging
        mock_audit.log_attempt.assert_called_once()
        assert "booking_date_modification" in mock_audit.log_attempt.call_args.kwargs["action"]

        # Verify signal was sent (notify_guest=True)
        mock_signal.send.assert_called_once()


# ----------------------------------------------------------------------
# UNIT: check_availability_for_dates (AvailabilityService)
# ----------------------------------------------------------------------

class TestCheckAvailabilityForDates:
    @patch("app.accommodation.services.availability_service.AvailabilityService.get_available_units", return_value=0)
    def test_room_type_scoped_unavailable(self, mock_get_units):
        from app.accommodation.services.availability_service import AvailabilityService

        result = AvailabilityService.check_availability_for_dates(
            property_id=1,
            check_in=date.today() + timedelta(days=10),
            check_out=date.today() + timedelta(days=12),
            room_type_id=1,
            units_needed=1,
        )
        assert result[0] is False
        assert "unit" in result[2].lower()

    @patch("app.accommodation.services.availability_service.AvailabilityService.get_available_units", return_value=2)
    def test_room_type_scoped_available(self, mock_get_units):
        from app.accommodation.services.availability_service import AvailabilityService

        result = AvailabilityService.check_availability_for_dates(
            property_id=1,
            check_in=date.today() + timedelta(days=10),
            check_out=date.today() + timedelta(days=12),
            room_type_id=1,
            units_needed=1,
        )
        assert result[0] is True
        assert result[2] is None

    def test_reverse_range_rejected(self):
        from app.accommodation.services.availability_service import AvailabilityService

        result = AvailabilityService.check_availability_for_dates(
            property_id=1,
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=3),
        )
        assert result[0] is False
        assert "Check-out must be after check-in" in result[2]

    def test_zero_nights_rejected(self):
        from app.accommodation.services.availability_service import AvailabilityService

        check_in = date.today() + timedelta(days=5)
        result = AvailabilityService.check_availability_for_dates(
            property_id=1,
            check_in=check_in,
            check_out=check_in,
        )
        assert result[0] is False
        assert "Check-out must be after check-in" in result[2]
