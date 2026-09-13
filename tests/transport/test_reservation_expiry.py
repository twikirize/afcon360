"""TH-3-D3 Batch 2 expiry regression coverage."""
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.transport.models import TransportReservation, TransportReservationLine
from app.transport.services.reservation_expiry_service import TransportReservationExpiryService


def test_expiry_releases_only_due_unpaid_held_reservation(db_session):
    reservation = TransportReservation(
        reservation_reference="RSVEXPIRY001", idempotency_key="expiry-001", request_fingerprint="a" * 64,
        reserving_user_id=1, offering_code="van", provider_type="organisation", provider_id=1,
        window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc) + timedelta(hours=1),
        required_quantity=1, mode="capacity", state="held", obligation_state="unpaid",
        deposit_required=True, deposit_due_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db.session.add(reservation); db.session.flush()
    db.session.add(TransportReservationLine(reservation_id=reservation.id, offering_code="van",
                   window_start=reservation.window_start, window_end=reservation.window_end, state="held"))
    db.session.commit()
    assert TransportReservationExpiryService.expire_due_held_reservations() == {"examined": 1, "expired": 1, "skipped": 0}
    assert db.session.get(TransportReservation, reservation.id).state == "expired"
    assert db.session.query(TransportReservationLine).filter_by(reservation_id=reservation.id).one().state == "cancelled"
    assert TransportReservationExpiryService.expire_due_held_reservations() == {"examined": 0, "expired": 0, "skipped": 0}
