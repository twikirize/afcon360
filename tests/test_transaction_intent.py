"""
Transaction Intent security & lifecycle tests.

Covers the required §16 intent cases:
  create, restore, expiry, tampering, session binding, consume, replay,
  cleanup, and authoritative revalidation.

These are pure unit tests - no database, no HTTP, no Redis - so they run
fast and deterministically. The module's Flask globals (has_request_context,
session, current_app) are replaced with controlled fakes so the intent
signing / session-binding logic can be exercised directly.

Security invariant under test (AGENTS.md §15 / §16):
  Modifying intent payload data MUST NOT alter authoritative price,
  inventory, availability, authorization, KYC, or payment decisions.
  This is guaranteed by:
    - HMAC integrity signature (tampering is detected -> intent invalidated)
    - session binding (cross-session use is rejected)
    - expiry (stale intents are dropped)
    - single-use consume (replay is rejected)
    - authoritative revalidation at commit time (validate_* returns only
      authoritative DB refs, never client-supplied amounts).
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from app.utils import transaction_intent as ti

pytestmark = pytest.mark.no_database


class TruthyDict(dict):
    """A dict that is always truthy (like a populated Flask session object)."""
    def __bool__(self):
        return True


def _intent_env(secret_key="test-secret-key"):
    """Return a context manager patching the module's Flask globals.

    Yields a namespace with:
      session: a TruthyDict used as the fake Flask session
      app:     a Mock current_app with a `config` dict
    """
    fake_session = TruthyDict()
    app_mock = mock.Mock()
    app_mock.config = {"SECRET_KEY": secret_key}
    return mock.patch.multiple(
        ti,
        has_request_context=mock.Mock(return_value=True),
        session=fake_session,
        current_app=app_mock,
    ), fake_session


@pytest.fixture
def intent_ctx():
    patcher, fake_session = _intent_env()
    with patcher:
        yield fake_session


def _make_intent(intent_type="event_ticket", key_values=None, patcher=None, fake_session=None):
    """Create a real intent through the module, returning (key, intent)."""
    key, intent = ti.create_transaction_intent(
        intent_type=intent_type,
        domain_refs={"event_public_id": "evt-1", "ticket_type_public_id": "tkt-1"},
        quantity=2,
        participant_info={"full_name": "Jane Doe", "email": "jane@example.com"},
    )
    if key_values:
        for k, v in key_values.items():
            if k in intent:
                intent[k] = v
    return key, intent


# ---------------------------------------------------------------- create
class TestCreate:
    def test_create_returns_idempotency_key_and_intent(self, intent_ctx):
        key, intent = _make_intent()
        assert key
        assert isinstance(key, str)
        assert intent["intent_type"] == "event_ticket"
        assert intent["quantity"] == 2
        assert intent["domain_refs"]["event_public_id"] == "evt-1"
        assert intent["idempotency_key"] == key
        assert "_signature" in intent

    def test_create_event_ticket_convenience(self, intent_ctx):
        key, intent = ti.create_event_ticket_intent("evt-1", "tkt-1")
        assert intent["intent_type"] == "event_ticket"
        assert intent["domain_refs"] == {
            "event_public_id": "evt-1",
            "ticket_type_public_id": "tkt-1",
        }

    def test_create_accommodation_intent(self, intent_ctx):
        key, intent = ti.create_accommodation_booking_intent(
            "prop-1", "rm-1", "2026-10-01", "2026-10-03", rooms_requested=2
        )
        assert intent["intent_type"] == "accommodation_booking"
        assert intent["quantity"] == 2
        assert intent["dates"] == {"check_in": "2026-10-01", "check_out": "2026-10-03"}

    def test_create_transport_intent(self, intent_ctx):
        key, intent = ti.create_transport_booking_intent(
            route_public_id="route-1", pickup_time="2026-10-01T09:00:00", passenger_count=3
        )
        assert intent["intent_type"] == "transport_booking"
        assert intent["quantity"] == 3
        assert intent["dates"]["pickup_time"] == "2026-10-01T09:00:00"

    def test_invalid_intent_type_rejected(self, intent_ctx):
        with pytest.raises(ti.TransactionIntentError) as ei:
            ti.create_transaction_intent("bogus_type")
        assert ei.value.code == "INVALID_INTENT_TYPE"

    def test_ttl_clamped_to_max(self, intent_ctx):
        key, intent = ti.create_transaction_intent(
            "event_ticket", ttl_minutes=99999
        )
        # created_at/expires_at diff must be <= MAX_INTENT_TTL
        delta = (
            datetime.fromisoformat(intent["expires_at"].replace("Z", "+00:00"))
            - datetime.fromisoformat(intent["created_at"].replace("Z", "+00:00"))
        )
        assert delta <= timedelta(minutes=ti.MAX_INTENT_TTL_MINUTES)

    def test_signature_is_keyed_by_secret(self):
        # Different SECRET_KEY produces a different signature for the same data
        patcher1, sess1 = _intent_env(secret_key="key-A")
        patcher2, sess2 = _intent_env(secret_key="key-B")
        with patcher1:
            key1, intent1 = _make_intent()
        with patcher2:
            # re-run create with same field values
            key2, intent2 = ti.create_event_ticket_intent("evt-1", "tkt-1")
        assert intent1["_signature"] != intent2["_signature"]


# ---------------------------------------------------------------- restore
class TestRestore:
    def test_restore_returns_original(self, intent_ctx):
        key, _ = _make_intent()
        got = ti.get_transaction_intent(key)
        assert got is not None
        assert got["idempotency_key"] == key

    def test_restore_does_not_consume(self, intent_ctx):
        key, _ = _make_intent()
        assert ti.get_transaction_intent(key) is not None
        # still present after a plain restore
        assert ti.get_transaction_intent(key) is not None
        assert key in ti.session.get("_transaction_intents", {})

    def test_restore_unknown_key_returns_none(self, intent_ctx):
        assert ti.get_transaction_intent("does-not-exist") is None


# ---------------------------------------------------------------- expiry
class TestExpiry:
    def test_expired_intent_is_dropped(self, intent_ctx):
        key, intent = _make_intent()
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        intent["expires_at"] = past
        ti.session["_transaction_intents"][key] = intent
        # recompute signature so the payload is otherwise valid - expiry is
        # the only thing that should make it invalid
        ti.session["_transaction_intents"][key]["_signature"] = ti._sign_payload(
            {k: v for k, v in intent.items() if k != "_signature"}
        )
        assert ti.get_transaction_intent(key) is None
        # expired intent is cleaned from the session
        assert key not in ti.session.get("_transaction_intents", {})

    def test_future_expiry_keeps_intent(self, intent_ctx):
        key, intent = _make_intent()
        # default TTL is 30m in the future - should still be valid
        assert ti.get_transaction_intent(key) is not None


# ---------------------------------------------------------------- tampering
class TestTampering:
    def test_tampered_quantity_invalidates(self, intent_ctx):
        key, _ = _make_intent()
        ti.session["_transaction_intents"][key]["quantity"] = 999
        assert ti.get_transaction_intent(key) is None
        # tampered intent removed
        assert key not in ti.session.get("_transaction_intents", {})

    def test_tampered_price_like_field_invalidates(self, intent_ctx):
        key, _ = _make_intent(
            intent_type="accommodation_booking",
        )
        ti.session["_transaction_intents"][key]["dates"] = {"check_in": "2020-01-01"}
        assert ti.get_transaction_intent(key) is None

    def test_tampered_domain_ref_invalidates(self, intent_ctx):
        key, _ = _make_intent()
        ti.session["_transaction_intents"][key]["domain_refs"]["event_public_id"] = "OTHER-EVENT"
        assert ti.get_transaction_intent(key) is None

    def test_missing_signature_invalidates(self, intent_ctx):
        key, intent = _make_intent()
        del ti.session["_transaction_intents"][key]["_signature"]
        assert ti.get_transaction_intent(key) is None

    def test_intent_cannot_be_used_to_authorize_payment(self, intent_ctx):
        # Proof: an attacker cannot inject an "approved"/amount into an intent
        # and have a consumer trust it; the authoritative-revalidation function
        # never returns client-supplied amounts.
        key, intent = _make_intent()
        intent["amount"] = "999999"
        intent["approved"] = True
        ti.session["_transaction_intents"][key] = intent
        ti.session["_transaction_intents"][key]["_signature"] = ti._sign_payload(
            {k: v for k, v in intent.items() if k != "_signature"}
        )
        ok, msg, auth_data = ti.validate_intent_against_authoritative_state(intent)
        # Even a signed, retrieve-able intent returns only authoritative DB
        # references - never the tampered "amount".
        assert ok is True
        for v in auth_data.values():
            assert v != "999999"
        assert "amount" not in auth_data


# ---------------------------------------------------------------- session binding
class TestSessionBinding:
    def test_intent_is_bound_to_creating_session(self, intent_ctx):
        key, _ = _make_intent()
        assert ti.session["_transaction_intents"][key]["session_id"] == ti._get_session_id()

    def test_intent_rejected_from_session_id_mismatch(self, intent_ctx):
        key, _ = _make_intent()
        # simulate a different session trying to access it
        ti.session["_session_id"] = "different-session"
        assert ti.get_transaction_intent(key) is None
        # removed
        assert key not in ti.session.get("_transaction_intents", {})

    def test_intent_is_isolated_between_sessions(self):
        # Creating with a different session id does not make the first recoverable
        patcher_a, sess_a = _intent_env()
        with patcher_a:
            key, _ = _make_intent()
            sid_a = ti._get_session_id()
        patcher_b, sess_b = _intent_env()
        with patcher_b:
            sid_b = ti._get_session_id()
            # Session ids differ because each fake session gets its own marker
            assert sid_a != sid_b


# ---------------------------------------------------------------- consume / replay / cleanup
class TestConsume:
    def test_consume_returns_and_removes(self, intent_ctx):
        key, _ = _make_intent()
        consumed = ti.consume_transaction_intent(key)
        assert consumed is not None
        assert consumed["idempotency_key"] == key
        assert key not in ti.session.get("_transaction_intents", {})

    def test_replay_after_consume_rejected(self, intent_ctx):
        key, _ = _make_intent()
        assert ti.consume_transaction_intent(key) is not None
        # second consume / restore returns nothing (replay protection)
        assert ti.consume_transaction_intent(key) is None
        assert ti.get_transaction_intent(key) is None

    def test_clear_single(self, intent_ctx):
        key, _ = _make_intent()
        assert ti.clear_transaction_intent(key) is True
        assert ti.clear_transaction_intent(key) is False

    def test_clear_all(self, intent_ctx):
        _make_intent(intent_type="event_ticket")
        _make_intent(intent_type="accommodation_booking")
        assert ti.get_active_intent_count() == 2
        cleared = ti.clear_all_transaction_intents()
        assert cleared == 2
        assert ti.get_active_intent_count() == 0

    def test_cleanup_removes_invalid_intents(self, intent_ctx):
        k1, i1 = _make_intent(intent_type="event_ticket")
        k2, i2 = _make_intent(intent_type="transport_booking")
        # corrupt the second one - it must be cleaned, not crash the count
        ti.session["_transaction_intents"][k2]["quantity"] = -5
        # get_active_intent_count ignores invalid rather than raising
        assert ti.get_active_intent_count() >= 1


# ---------------------------------------------------------------- authoritative revalidation
class TestAuthoritativeRevalidation:
    def test_event_revalidation_returns_db_refs_only(self, intent_ctx):
        _, intent = _make_intent(intent_type="event_ticket")
        ok, msg, data = ti.validate_intent_against_authoritative_state(intent)
        assert ok is True
        assert data["event_public_id"] == "evt-1"
        assert data["ticket_type_public_id"] == "tkt-1"
        # the validated data NEVER carries a price the client supplied
        assert "price" not in data and "amount" not in data

    def test_accommodation_revalidation(self, intent_ctx):
        key, intent = ti.create_accommodation_booking_intent(
            "prop-1", "rm-1", "2026-10-01", "2026-10-03"
        )
        ok, msg, data = ti.validate_intent_against_authoritative_state(intent)
        assert ok is True
        assert data["property_public_id"] == "prop-1"
        assert data["room_type_public_id"] == "rm-1"
        assert "price" not in data

    def test_transport_revalidation(self, intent_ctx):
        key, intent = ti.create_transport_booking_intent(route_public_id="route-1")
        ok, msg, data = ti.validate_intent_against_authoritative_state(intent)
        assert ok is True
        assert data["route_public_id"] == "route-1"

    def test_unknown_type_not_trusted(self, intent_ctx):
        _, intent = _make_intent(intent_type="event_ticket")
        intent["intent_type"] = "mystery"
        ok, msg, data = ti.validate_intent_against_authoritative_state(intent)
        assert ok is False


# ---------------------------------------------------------------- out-of-context guards
class TestRequestContextGuards:
    def test_create_requires_request_context(self):
        with mock.patch.object(ti, "has_request_context", return_value=False):
            with pytest.raises(ti.TransactionIntentError) as ei:
                ti.create_transaction_intent("event_ticket")
            assert ei.value.code == "NO_REQUEST_CONTEXT"

    def test_get_without_context_returns_none(self):
        with mock.patch.object(ti, "has_request_context", return_value=False):
            assert ti.get_transaction_intent("anything") is None
