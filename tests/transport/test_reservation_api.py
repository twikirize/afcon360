"""Reservation API contract smoke tests live alongside the D3 service suite.

Detailed authentication fixtures are supplied by the repository-wide API test
matrix; these assertions pin the public serialization boundary locally.
"""
from datetime import datetime, timezone

from app.transport.api.reservation_routes import _reservation_data


def test_public_reservation_serialization_excludes_internal_identifiers():
    class Reservation:
        reservation_reference = "RSVAPI001"; offering_code = "van"; window_start = datetime.now(timezone.utc)
        window_end = datetime.now(timezone.utc); required_quantity = 1; mode = "capacity"; state = "held"
        obligation_state = "unpaid"; payment_method = "CARD"; payment_timing = "NOW"; deposit_required = False
        deposit_amount = deposit_currency = deposit_due_at = required_total_amount = None; amount_received = 0
        id = vehicle_id = provider_id = reserving_user_id = on_behalf_of_organisation_id = 99
    data = _reservation_data(Reservation())
    assert data["reservation_reference"] == "RSVAPI001"
    assert not {"id", "vehicle_id", "provider_id", "reserving_user_id", "on_behalf_of_organisation_id"} & set(data)
