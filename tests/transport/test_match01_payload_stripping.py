"""MATCH-01: rider payload stripping (control-authorized gap test).

Non-admin rider payloads must not expose ``no_match_reason``,
``offer_attempts`` (durable offer ledger), or ``audit_log``; the
authorized/admin payload keeps them. Smallest focused proof through the
real HTTP endpoint — the API implementation is unchanged.
"""
import pytest

from app.extensions import db
from tests.transport.test_match01_no_match_terminals import _backdate_window
from tests.transport.test_match01_silent_rejection import (
    _patch_redis,
    _seed_confirmed_booking,
    _seed_rider,
)

pytestmark = pytest.mark.usefixtures("db_session")


class TestRiderPayloadStripping:
    def test_rider_payload_omits_matching_internals(
            self, app, client, admin_client, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from app.transport.services.matching_service import MatchingService
        from app.transport.services.offer_service import OfferService
        from tests.test_geo_rider_tracking import _rider_client

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context():
            stored = db.session.get(Booking, booking_id)
            OfferService.create_offer(ref, 101, 501)
            assert OfferService.decline_offer(ref, 101) is True
            attempts = (db.session.get(Booking, booking_id)
                        .booking_metadata.get("offer_attempts"))
            assert attempts, "ledger must hold the declined attempt"
        _backdate_window(app, booking_id, minutes=5)
        with app.app_context():
            outcome = MatchingService.check_matching_outcome(booking_id)
            assert outcome["reason"] == "all_rejected"

        # ---- rider client: a **fresh** client distinct from admin_client ----
        rider_client = app.test_client()
        _rider_client(app, rider_client, rider_id)
        resp = rider_client.get(f"/api/transport/bookings/{ref}")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        payload = resp.get_json()["data"]["booking"]
        assert payload["status"] == BookingStatus.NO_MATCH.value
        assert "no_match_reason" not in payload
        assert "audit_log" not in payload
        meta = payload.get("booking_metadata") or {}
        assert "offer_attempts" not in meta

        # ---- admin client (already logged in as owner) ----
        with admin_client.session_transaction() as sess:
            sess["active_global_role"] = "owner"
        admin_resp = admin_client.get(f"/api/transport/bookings/{ref}")
        assert admin_resp.status_code == 200, \
            admin_resp.get_data(as_text=True)
        admin_payload = admin_resp.get_json()["data"]["booking"]
        assert admin_payload["no_match_reason"] == "all_rejected"
        admin_meta = admin_payload.get("booking_metadata") or {}
        assert admin_meta.get("offer_attempts"), \
            "admin payload keeps the durable ledger"
        assert admin_payload.get("audit_log"), \
            "admin payload keeps the audit trail"
