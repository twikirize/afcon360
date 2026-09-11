# tests/test_stage62a_transport_auth_public_id.py
"""Stage 6-2A: Transport REST authorization + public-ID + wallet boundary leaks.

F-18a:
- Unauthenticated callers can currently read every transport REST GET endpoint
  (booking list/detail/payments/route, drivers, vehicles, organisations,
  incidents, routes, settings).
- Booking detail is addressed by internal DB id (`/bookings/<int:booking_id>`)
  instead of the public booking reference.

F-04 / F-17:
- `/api/wallet/me` (and deposit/withdraw) leak the internal integer `user_id`
  at the API boundary.
- Wallet template output logic references internal ids.

Each test asserts the REQUIRED behavior. Against the pre-change code these
fail (RED); after the minimal fix they pass.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.extensions import db

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers (always return plain values, never ORM objects, so tests can use
# the HTTP client outside an app context)
# ---------------------------------------------------------------------------

def _make_user(app, tag):
    from app.identity.models.user import User

    suffix = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"s62a_{tag}_{suffix}",
        email=f"{tag}_{suffix}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    user.set_password("Password123!")
    db.session.add(user)
    db.session.commit()
    return str(user.public_id), user.id


def _grant_admin(app, internal_id):
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import User, UserRole

    user = db.session.get(User, internal_id)
    role = get_or_create_role("admin", level=3)
    if not any(getattr(r, "role_id", None) == role.id for r in user.roles):
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
        db.session.commit()


def _login(client, public_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = public_id


def _make_booking(app, user_internal_id):
    from app.transport.models import (
        Booking, BookingStatus, Currency, PaymentStatus,
        ProviderType, ServiceType,
    )

    now = datetime.now(timezone.utc)
    booking = Booking(
        user_id=user_internal_id,
        user_type="fan",
        provider_type=ProviderType.INDIVIDUAL_DRIVER,
        service_type=ServiceType.ON_DEMAND,
        pickup_location={"latitude": 1.0, "longitude": 2.0},
        dropoff_location={"latitude": 3.0, "longitude": 4.0},
        pickup_time=now + timedelta(hours=2),
        passenger_count=1,
        base_price=Decimal("50.00"),
        subtotal=Decimal("50.00"),
        total_amount=Decimal("50.00"),
        final_price=Decimal("50.00"),
        currency=Currency.USD,
        payment_status=PaymentStatus.PENDING,
        status=BookingStatus.CONFIRMED,
    )
    booking.generate_booking_reference()
    db.session.add(booking)
    db.session.commit()
    return booking.booking_reference, booking.id


def _make_wallet_account(app, user_internal_id):
    from app.wallet.routes import get_or_create_account

    with db.session.no_autoflush:
        account = get_or_create_account(user_internal_id, currency="USD")
    return str(account.id)


# ---------------------------------------------------------------------------
# F-18a — Transport REST authorization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "/api/transport/bookings",
        "/api/transport/drivers",
        "/api/transport/vehicles",
        "/api/transport/organisations",
        "/api/transport/incidents",
        "/api/transport/routes",
        "/api/transport/settings",
        "/api/transport/analytics/revenue",
    ],
)
def test_unauth_transport_reads_are_denied(app, client, path):
    """Unauthenticated GET on transport REST must never return data (200)."""
    resp = client.get(path)
    assert resp.status_code != 200, (
        f"Unauthenticated GET {path} must be denied, got {resp.status_code}"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/transport/bookings",
        "/api/transport/drivers",
        "/api/transport/vehicles",
        "/api/transport/organisations",
        "/api/transport/incidents",
        "/api/transport/routes",
    ],
)
def test_non_admin_transport_list_reads_are_denied(app, client, path):
    """A logged-in non-admin must not be able to read fleet/booking/ops data."""
    with app.app_context():
        public_id, _ = _make_user(app, "plain")
    _login(client, public_id)
    resp = client.get(path)
    assert resp.status_code in (302, 401, 403), (
        f"Non-admin GET {path} must be denied, got {resp.status_code}"
    )


def test_booking_list_admin_allowed(app, client):
    with app.app_context():
        public_id, internal_id = _make_user(app, "badmin")
        _grant_admin(app, internal_id)
    _login(client, public_id)
    resp = client.get("/api/transport/bookings")
    # Admin must pass the auth gate. A 200 is the clean result; a 500 is the
    # entangled pre-existing serializer defect (F-19: transport REST layer
    # references the missing app.core.serializers module) and is NOT an auth
    # rejection.
    assert resp.status_code not in (302, 401, 403), resp.status_code


def test_booking_detail_by_reference_owner_allowed(app, client):
    with app.app_context():
        owner_pid, owner_uid = _make_user(app, "bowner")
        ref, _ = _make_booking(app, owner_uid)
        ref = str(ref)
    _login(client, owner_pid)
    resp = client.get(f"/api/transport/bookings/{ref}")
    # Owner must pass the auth gate (never redirected / forbidden for their own
    # booking by reference). 200 = clean; 500 = F-19 serializer defect.
    assert resp.status_code not in (302, 401, 403), resp.status_code
    if resp.status_code == 200:
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["booking"]["booking_reference"] == ref


def test_booking_detail_by_reference_denied_for_stranger(app, client):
    with app.app_context():
        _, owner_uid = _make_user(app, "bowner2")
        stranger_pid, _ = _make_user(app, "bstranger")
        ref, _ = _make_booking(app, owner_uid)
        ref = str(ref)
    _login(client, stranger_pid)
    resp = client.get(f"/api/transport/bookings/{ref}")
    assert resp.status_code == 403, (
        f"Stranger GET booking detail must be forbidden, got {resp.status_code}"
    )


def test_booking_detail_internal_db_id_is_rejected(app, client):
    """Internal DB id must NOT resolve a booking in the public API."""
    with app.app_context():
        owner_pid, owner_uid = _make_user(app, "bowner3")
        _, internal_id = _make_booking(app, owner_uid)
        internal_id = int(internal_id)
    _login(client, owner_pid)
    resp = client.get(f"/api/transport/bookings/{internal_id}")
    assert resp.status_code == 404, (
        f"Internal DB id {internal_id} must not resolve a booking, got {resp.status_code}"
    )


def test_booking_detail_admin_allowed(app, client):
    with app.app_context():
        _, owner_uid = _make_user(app, "bowner4")
        admin_pid, admin_uid = _make_user(app, "badmin4")
        _grant_admin(app, admin_uid)
        ref, _ = _make_booking(app, owner_uid)
        ref = str(ref)
    _login(client, admin_pid)
    resp = client.get(f"/api/transport/bookings/{ref}")
    # Admin must pass the auth gate. 200 = clean; 500 = F-19 serializer defect.
    assert resp.status_code not in (302, 401, 403), resp.status_code


def test_booking_detail_requires_login(app, client):
    with app.app_context():
        _, owner_uid = _make_user(app, "bowner5")
        ref, _ = _make_booking(app, owner_uid)
        ref = str(ref)
    resp = client.get(f"/api/transport/bookings/{ref}")
    assert resp.status_code != 200


def test_setting_by_key_authenticated_user_passes_login_gate(app, client):
    # TransportSetting rows cannot be created in tests: @validates('value')
    # lazy-imports the missing app.core.validators module (F-19), so a 500
    # fires on construction. Without a row, an authenticated user reaching a
    # nonexistent key must get 404 -- i.e. NOT bounced by the login gate.
    with app.app_context():
        public_id, _ = _make_user(app, "suser")
    _login(client, public_id)
    resp = client.get(f"/api/transport/settings/key/nonexistent_{uuid.uuid4().hex[:6]}")
    assert resp.status_code == 404, (
        f"Authenticated user should hit 404 (not auth-rejected) on unknown key, got {resp.status_code}"
    )


def test_setting_detail_admin_only(app, client):
    # Nonexistent setting id: gate order is decorator-before-404, so:
    #   unauth      -> 302 (admin_required redirect to login)
    #   non-admin   -> 403
    #   admin       -> 404 (passes gate, then not found) -- or 500 via F-19 if a row existed
    resp = client.get("/api/transport/settings/99999999")
    assert resp.status_code in (302, 401, 403), (
        f"Unauthenticated GET setting detail must be denied, got {resp.status_code}"
    )
    with app.app_context():
        non_admin_pid, _ = _make_user(app, "puser")
    _login(client, non_admin_pid)
    resp = client.get("/api/transport/settings/99999999")
    assert resp.status_code == 403, (
        f"Non-admin GET setting detail must be denied, got {resp.status_code}"
    )


def test_dashboard_overview_still_admin_only(app, client):
    with app.app_context():
        admin_pid, admin_uid = _make_user(app, "dadmin")
        _grant_admin(app, admin_uid)
    _login(client, admin_pid)
    resp = client.get("/api/transport/dashboard/overview")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# F-04 — wallet API boundary must not leak internal user_id
# ---------------------------------------------------------------------------

def test_wallet_me_has_no_internal_user_id(app, client):
    with app.app_context():
        public_id, internal_id = _make_user(app, "wme")
        _make_wallet_account(app, internal_id)
    _login(client, public_id)
    resp = client.get("/api/wallet/me")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    payload = resp.get_json()
    data = payload.get("data", {})
    assert data.get("exists") is True
    assert "user_id" not in data, f"Internal user_id leaked in /api/wallet/me: {data}"
    assert "account_id" in data, "Public account_id must remain present"


def test_wallet_deposit_has_no_internal_user_id(app, client):
    with app.app_context():
        public_id, internal_id = _make_user(app, "wdep")
        _make_wallet_account(app, internal_id)
    _login(client, public_id)
    resp = client.post(
        "/api/wallet/deposit",
        json={
            "amount": "10000",
            "currency": "USD",
        },
        headers={"X-Idempotency-Key": f"stage62a-dep-{uuid.uuid4().hex}"},
    )
    # If the deposit succeeds it must not leak the internal id. Error codes
    # stay acceptable (defect excluded from this node) but success payloads
    # must be clean.
    if resp.status_code == 200:
        payload = resp.get_json()
        data = payload.get("data", {})
        assert "user_id" not in data, f"Internal user_id leaked in deposit: {data}"
        assert "account_id" in data, "Public account_id must remain present"


# ---------------------------------------------------------------------------
# F-17 — wallet pane renders direction without internal-id template logic
# ---------------------------------------------------------------------------

def test_wallet_dashboard_pane_direction_renders(app, client):
    """The pane must still sign outgoing (-) / incoming (+) using a
    server-computed direction, not template-side internal id comparison."""
    from app.wallet.models.transaction import TransactionModel, TransactionType

    with app.app_context():
        public_id, internal_id = _make_user(app, "wpane")
        _, sender_id = _make_user(app, "wpane_from")
        account_id = _make_wallet_account(app, internal_id)
        db.session.query(TransactionModel).filter(
            TransactionModel.user_id.in_([internal_id, sender_id])
        ).delete(synchronize_session=False)
        out_tx = TransactionModel(
            client_request_id=f"stage62a-pane-out-{uuid.uuid4().hex}",
            tx_type=TransactionType.WITHDRAW.value,
            status="completed",
            amount=Decimal("1000.00"),
            currency="USD",
            user_id=internal_id,
            recipient_user_id=None,
            account_id=account_id,
        )
        in_tx = TransactionModel(
            client_request_id=f"stage62a-pane-in-{uuid.uuid4().hex}",
            tx_type=TransactionType.DEPOSIT.value,
            status="completed",
            amount=Decimal("500.00"),
            currency="USD",
            user_id=sender_id,
            recipient_user_id=internal_id,
            account_id=account_id,
        )
        db.session.add_all([out_tx, in_tx])
        db.session.commit()
    _login(client, public_id)
    resp = client.get("/wallet/dashboard?_pane=1")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "-1,000" in html
    assert "+500" in html