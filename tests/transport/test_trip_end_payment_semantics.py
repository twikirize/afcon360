"""Transport settlement is separate from the ride lifecycle."""
from datetime import datetime, timezone

import pytest

from app.extensions import db
from app.transport.models import Booking, BookingStatus, PaymentStatus, ProviderType, ServiceType
from app.transport.services.payment_service import PaymentService
from app.utils.exceptions import ValidationError

pytestmark = pytest.mark.usefixtures("db_session")


def _booking(user_id, status, method="cash"):
    booking = Booking(
        user_id=user_id,
        provider_type=ProviderType.INDIVIDUAL_DRIVER,
        service_type=ServiceType.ON_DEMAND,
        pickup_location={"address": "Pickup"},
        dropoff_location={"address": "Destination"},
        pickup_time=datetime.now(timezone.utc),
        passenger_count=1,
        base_price=25,
        subtotal=25,
        total_amount=25,
        final_price=25,
        payment_method=method,
        payment_status=PaymentStatus.PENDING,
        status=status,
    )
    db.session.add(booking)
    db.session.commit()
    return booking.id


def _payment_payload(method="cash"):
    return {"amount": "25.00", "currency": "USD", "payment_method": method}


def test_settlement_rejected_before_trip_completion(app, test_user, monkeypatch):
    with app.app_context():
        user_id = db.session.merge(test_user).id
        booking_id = _booking(user_id, BookingStatus.IN_PROGRESS)
        monkeypatch.setattr(
            PaymentService, "_validate_payment_method", staticmethod(lambda booking, method: None)
        )

        with pytest.raises(ValidationError, match="only after the trip is completed"):
            PaymentService.process_payment(booking_id, _payment_payload())

        db.session.expire_all()
        booking = db.session.get(Booking, booking_id)
        assert booking.status == BookingStatus.IN_PROGRESS.value
        assert booking.payment_status == PaymentStatus.PENDING.value
        assert booking.payment_captured_at is None


def test_cash_stays_pending_after_trip_completion_until_receipt_confirmed(
    app, test_user, monkeypatch
):
    with app.app_context():
        user_id = db.session.merge(test_user).id
        booking_id = _booking(user_id, BookingStatus.COMPLETED, "cash")
        monkeypatch.setattr(
            PaymentService, "_validate_payment_method", staticmethod(lambda booking, method: None)
        )

        result = PaymentService.process_payment(booking_id, _payment_payload("cash"))
        db.session.expire_all()
        booking = db.session.get(Booking, booking_id)

        assert result["success"] is True
        assert result["data"]["payment_status"] == "pending"
        assert result["data"]["requires_cash_receipt_confirmation"] is True
        assert booking.status == BookingStatus.COMPLETED.value
        assert booking.payment_status == PaymentStatus.PENDING.value
        assert booking.payment_captured_at is None
        assert booking.payment_gateway_reference is None
