"""UI-16 — No-Match Experience regression coverage.

UI-16-A: the client polling-budget timeout must read as in-progress work,
never as a terminal no-match verdict, and its action must only resume
polling (no second booking, no server retry call).

Part 1 (pure-file, no DB): pins the rider-visible timeout copy/action in
static/js/modules/transport/rider_matching.js and the intact server-side
terminal branch in templates/transport/rides/show.html.

Part 2 (real Flask handler): the genuine retry route — flash, redirect,
ownership, duplicate-retry protection — plus server rendering of the
reason-specific terminal branch. Reuses MATCH-01 seed helpers; no mocks
except the established fake-Redis patch.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATCHING_JS = ROOT / "static" / "js" / "modules" / "transport" / "rider_matching.js"
SHOW_HTML = ROOT / "templates" / "transport" / "rides" / "show.html"


def _js() -> str:
    return MATCHING_JS.read_text(encoding="utf-8")


def _show() -> str:
    return SHOW_HTML.read_text(encoding="utf-8")


# --- Part 1: client timeout copy/action (UI-16-A) -----------------------------

class TestUI16AClientTimeoutCopy:
    def test_timeout_copy_is_in_progress_not_terminal(self):
        js = _js()
        assert "Still checking for drivers. " in js
        assert "This is taking longer than expected." in js
        # The old terminal-sounding verdict must be gone.
        assert "No drivers available right now" not in js

    def test_timeout_action_resumes_polling_only(self):
        js = _js()
        assert "Keep checking" in js
        assert "Try Again" not in js
        # The resume control is a plain button (never a submit).
        assert "btn.type = 'button'" in js
        # The resume path touches no network booking/retry surface:
        # retrySearch restarts the existing pollers only.
        start = js.index("function retrySearch()")
        block = js[start:start + 1200]
        assert "fetch(" not in block
        assert "rides_retry_matching" not in block
        assert "/retry" not in block

    def test_connection_error_behavior_preserved(self):
        js = _js()
        assert "Connection issue" in js
        # Network failures still retry on cadence without spending budget
        # and never render a no-supply verdict.
        assert "noteFailure" in js


class TestUI16TerminalBranchIntact:
    def test_no_match_branch_and_reasons_intact(self):
        html = _show()
        assert 'id="riderNoMatch"' in html
        assert "No cars available right now" in html
        assert "Couldn't match this ride right now" in html
        assert "No match found" in html

    def test_genuine_retry_action_posts_to_retry_route(self):
        html = _show()
        assert "transport.rides_retry_matching" in html
        assert ">Try again</button>" in html

    def test_adjust_request_stays_all_rejected_only(self):
        html = _show()
        start = html.index('id="riderNoMatch"')
        branch = html[start:start + 2500]
        assert "Adjust request" in branch
        assert "no_match_reason == 'all_rejected'" in branch


# --- Part 2: genuine retry route (real Flask handler) -------------------------

def _to_no_supply(app, monkeypatch, booking_id):
    from tests.transport.test_match01_no_match_terminals import (
        _backdate_window,
    )
    from tests.transport.test_match01_silent_rejection import _patch_redis
    from app.transport.services.matching_service import MatchingService

    _patch_redis(monkeypatch)
    _backdate_window(app, booking_id, minutes=5)
    with app.app_context():
        outcome = MatchingService.check_matching_outcome(booking_id)
        assert outcome["reason"] == "no_supply"
        return outcome


class TestUI16RetryRoute:
    def test_retry_returns_to_ride_page_with_flash(
            self, app, client, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from tests.test_geo_rider_tracking import _rider_client
        from tests.transport.test_match01_silent_rejection import (
            _seed_confirmed_booking,
            _seed_rider,
        )

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _to_no_supply(app, monkeypatch, booking_id)
        _rider_client(app, client, rider_id)

        resp = client.post(f"/transport/rides/{ref}/retry",
                           follow_redirects=False)
        assert resp.status_code == 302
        assert f"/transport/rides/{ref}" in resp.headers["Location"]
        followed = client.get(resp.headers["Location"])
        html = followed.get_data(as_text=True)
        assert "Searching for drivers again" in html
        with app.app_context():
            stored = db_session_get(app, Booking, booking_id)
            assert stored.status == BookingStatus.CONFIRMED
            assert stored.no_match_reason is None

    def test_retry_from_confirmed_rejected_with_flash(
            self, app, client, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from tests.test_geo_rider_tracking import _rider_client
        from tests.transport.test_match01_silent_rejection import (
            _patch_redis,
            _seed_confirmed_booking,
            _seed_rider,
        )

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        _rider_client(app, client, rider_id)

        resp = client.post(f"/transport/rides/{ref}/retry",
                           follow_redirects=True)
        html = resp.get_data(as_text=True)
        assert "only available from no_match" in html
        with app.app_context():
            stored = db_session_get(app, Booking, booking_id)
            assert stored.status == BookingStatus.CONFIRMED

    def test_retry_forbidden_for_stranger(self, app, client, monkeypatch):
        from tests.test_geo_rider_tracking import _rider_client
        from tests.transport.test_match01_silent_rejection import (
            _seed_confirmed_booking,
            _seed_rider,
        )

        rider_id = _seed_rider(app)
        stranger_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _to_no_supply(app, monkeypatch, booking_id)
        _rider_client(app, client, stranger_id)

        resp = client.post(f"/transport/rides/{ref}/retry",
                           follow_redirects=False)
        assert resp.status_code == 403

    def test_second_retry_after_success_rejected(
            self, app, client, monkeypatch):
        from app.transport.models import Booking, BookingStatus
        from tests.test_geo_rider_tracking import _rider_client
        from tests.transport.test_match01_silent_rejection import (
            _seed_confirmed_booking,
            _seed_rider,
        )

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _to_no_supply(app, monkeypatch, booking_id)
        _rider_client(app, client, rider_id)

        first = client.post(f"/transport/rides/{ref}/retry",
                            follow_redirects=False)
        assert first.status_code == 302
        second = client.post(f"/transport/rides/{ref}/retry",
                             follow_redirects=True)
        assert "only available from no_match" in \
            second.get_data(as_text=True)
        with app.app_context():
            stored = db_session_get(app, Booking, booking_id)
            assert stored.status == BookingStatus.CONFIRMED

    def test_no_match_page_renders_reason_branch(
            self, app, client, monkeypatch):
        from tests.test_geo_rider_tracking import _rider_client
        from app.transport.services.booking_service import BookingService
        from tests.transport.test_match01_silent_rejection import (
            _patch_redis,
            _seed_confirmed_booking,
            _seed_rider,
        )

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _patch_redis(monkeypatch)
        with app.app_context():
            BookingService.mark_no_match(booking_id, "all_rejected",
                                         initiated_by="system")
        _rider_client(app, client, rider_id)

        html = client.get(f"/transport/rides/{ref}").data.decode("utf-8")
        assert "Couldn't match this ride right now" in html
        assert "No match found" in html
        assert "Try again" in html
        assert "Adjust request" in html
        lowered = html.lower()
        assert "rejected" not in lowered
        assert "declined" not in lowered
        assert "refused" not in lowered

    def test_no_supply_branch_copy(self, app, client, monkeypatch):
        from tests.test_geo_rider_tracking import _rider_client
        from tests.transport.test_match01_silent_rejection import (
            _seed_confirmed_booking,
            _seed_rider,
        )

        rider_id = _seed_rider(app)
        booking_id, ref = _seed_confirmed_booking(app, rider_id)
        _to_no_supply(app, monkeypatch, booking_id)
        _rider_client(app, client, rider_id)

        html = client.get(f"/transport/rides/{ref}").data.decode("utf-8")
        assert "No cars available right now" in html
        assert "No match found" in html
        assert "Try again" in html
        # Adjust-request is all_rejected-only.
        assert "Adjust request" not in html


def db_session_get(app, model, obj_id):
    from app.extensions import db
    with app.app_context():
        return db.session.get(model, obj_id)
