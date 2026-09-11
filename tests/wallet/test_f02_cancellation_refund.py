"""
F-02 Cancellation Refund Repair — RED→GREEN tests.

Proves the AttributeError at guest_cancel_booking route when calling
WalletService.refund_wallet (non-existent), then verifies the fix uses
MarketplaceService.refund_guest (canonical).
"""

import uuid
from decimal import Decimal
from datetime import date, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
    AccommodationPaymentStatus,
)
from app.accommodation.models.property import Property
from app.accommodation.models.room import RoomType
from app.accommodation.models.commission import BookingCommission
from app.accommodation.services.booking_service import BookingService
from app.accommodation.services.marketplace_service import MarketplaceService
from app.extensions import db
from app.identity.models.user import User

# ─── FIX: import typing for the return‑annotation check ───
from typing import Tuple, Optional


# ---------- Fixtures ----------
# `app`, `client` and `test_db` come from the central tests/conftest.py.

@pytest.fixture
def platform_org_id(app, test_db):
    """Set PLATFORM_ORG_ID for MarketplaceService."""
    with app.app_context():
        from app.identity.models.organisation import Organisation
        org = Organisation(
            org_id=f"PLATFORM-{uuid.uuid4().hex[:12]}",
            name="Platform",
            country="UG",
            legal_name=f"Platform Organisation {uuid.uuid4().hex[:8]}",
            org_type="platform",
            registration_no="PLAT-001",
            email="platform@test.com",
            phone="+256700000000",
            is_verified=True,
            is_active=True,
            is_operational=True,
            verification_status="verified",
        )
        db.session.add(org)
        db.session.commit()
        # MarketplaceService expects the internal BIGINT id
        app.config['PLATFORM_ORG_ID'] = str(org.id)
        yield org.id


@pytest.fixture
def test_host_user(app, test_db):
    user = User(
        email=f"host-{uuid.uuid4().hex[:6]}@example.com",
        username=f"host-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        kyc_level=2,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def test_guest_user(app, test_db):
    user = User(
        email=f"guest-{uuid.uuid4().hex[:6]}@example.com",
        username=f"guest-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        kyc_level=2,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def test_property(app, test_db, test_host_user, platform_org_id):
    prop = Property(
        title="Test Property",
        slug=f"test-property-{uuid.uuid4().hex[:8]}",
        description="Test property",
        address_line1="123 Test Street",
        city="Kampala",
        country="UG",
        status="active",
        is_verified=True,
        is_active=True,
        base_price_per_night=Decimal("100.00"),
        currency="USD",
        max_guests=4,
        instant_book=True,
        cancellation_policy="flexible",
        owner_user_id=test_host_user.id,
    )
    db.session.add(prop)
    db.session.commit()

    rt = RoomType(
        property_id=prop.id,
        name="Standard Room",
        description="Standard test room",
        max_guests=2,
        bedrooms=1,
        beds=1,
        bathrooms=1,
        base_price_per_night=Decimal("100.00"),
        currency="USD",
        total_units=10,
        is_active=True,
    )
    db.session.add(rt)
    db.session.commit()
    return prop


def _create_paid_booking(app, test_db, test_property, test_guest_user, test_host_user):
    """Create a booking with payment_status=PAID and a commission record (simulating charge_guest)."""
    booking = AccommodationBooking(
        property_id=test_property.id,
        guest_user_id=test_guest_user.id,
        host_user_id=test_host_user.id,
        check_in=date.today() + timedelta(days=3),
        check_out=date.today() + timedelta(days=5),
        num_nights=2,
        num_guests=2,
        nightly_rate=Decimal("100.00"),
        cleaning_fee=Decimal("20.00"),
        service_fee=Decimal("10.00"),
        total_amount=Decimal("230.00"),
        currency="USD",
        guest_name="Test Guest",
        guest_email="guest@test.com",
        guest_phone="+256700000000",
        payment_status=AccommodationPaymentStatus.PAID.value,
        status=AccommodationBookingStatus.CONFIRMED.value,
        booked_by_user_id=test_guest_user.id,
        booking_type="self",
        payment_timing="pay_now",
        payment_method="wallet",
        payment_guaranteed=True,
        guarantee_type="wallet_balance",
    )
    booking.generate_reference()
    db.session.add(booking)
    db.session.commit()

    # Simulate the charge_guest outcome: commission record + wallet_txn_id
    commission = BookingCommission(
        booking_id=booking.id,
        total_amount=booking.total_amount,
        commission_amount=Decimal("23.00"),
        host_payout=Decimal("207.00"),
        platform_fee_pct=Decimal("10.0"),
        status='held',
        extra_data={
            'booking_reference': booking.booking_reference,
            'property_id': str(booking.property_id),
            'guest_user_id': str(booking.booked_by_user_id),
            'host_user_id': str(booking.host_user_id),
            'commission_pct': '10.0',
            'commission_amount': '23.00',
            'host_payout': '207.00',
        }
    )
    db.session.add(commission)
    booking.wallet_txn_id = f"txn-charge-{uuid.uuid4().hex[:12]}"
    db.session.commit()
    return booking


# ─── FIX: session‑based login helpers (preserve existing) ───
def _login_as_guest(client, public_id):
    """Log in as guest user via session."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(public_id)
        sess['_fresh'] = True


def _login_as_host(client, public_id):
    """Log in as host user via session."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(public_id)
        sess['_fresh'] = True


# ---------- Tests ----------

class TestF02CancellationRefundContract:
    """Contract shape tests for the cancellation refund primitive."""

    def test_marketplace_service_has_refund_guest(self):
        """MarketplaceService.refund_guest exists and has correct signature."""
        import inspect
        sig = inspect.signature(MarketplaceService.refund_guest)
        params = list(sig.parameters.keys())
        assert params == ['booking_id', 'refund_amount']
        # ─── FIX: correct annotation check ───
        assert sig.return_annotation == Tuple[bool, Optional[str]]

    def test_wallet_service_has_no_refund_wallet(self):
        """WalletService.refund_wallet does NOT exist (the bug)."""
        from app.wallet.services.wallet_service import WalletService
        assert not hasattr(WalletService, 'refund_wallet'), (
            "WalletService.refund_wallet should not exist — use MarketplaceService.refund_guest instead"
        )


class TestGuestCancellationRoute:
    """HTTP route tests for guest cancellation with refund."""

    # ─── FIX: removed the RED test because the bug has already been fixed ───
    # (The GREEN test below now verifies the correct behaviour.)

    def test_cancel_with_refund_succeeds_after_fix(self, app, client, test_db, test_property, test_guest_user, test_host_user, platform_org_id):
        """
        GREEN: After fix, guest_cancel_booking uses MarketplaceService.refund_guest
        and returns success redirect.
        """
        with app.app_context():
            booking = _create_paid_booking(app, test_db, test_property, test_guest_user, test_host_user)
            booking_ref = booking.booking_reference
            guest_public_id = test_guest_user.public_id

        _login_as_guest(client, guest_public_id)

        # Patch MarketplaceService.refund_guest to avoid needing real wallet accounts
        with patch.object(MarketplaceService, 'refund_guest', return_value=(True, None)) as mock_refund:
            resp = client.post(
                f'/accommodation/guest/booking/{booking_ref}/cancel',
                data={'reason': 'Test cancellation'},
                follow_redirects=False
            )

            # Debug: check where it redirects
            print(f"DEBUG: response status={resp.status_code}, location={resp.location}")
            print(f"DEBUG: response data={resp.data[:500]}")

# Should redirect (302) on success
            assert resp.status_code == 302
            mock_refund.assert_called_once()
            args, kwargs = mock_refund.call_args
            assert args[0] == booking.id
            assert args[1] == Decimal("230.00")  # full refund for FLEXIBLE policy

    def test_cancel_no_refund_when_policy_zero(self, app, client, test_db, test_property, test_guest_user, test_host_user, platform_org_id):
        """Cancellation with SUPER_STRICT policy (0 refund) should NOT call refund_guest."""
        with app.app_context():
            booking = _create_paid_booking(app, test_db, test_property, test_guest_user, test_host_user)
            # The quote resolves the policy from the booking-time policy snapshot
            # (production writes the legacy tier name into it — see routes.py
            # `policy_snapshot` build). 'super_strict' has no matching canonical
            # CancellationPolicy row (names are FLEX/MOD/STRICT/SUPER/NOSHOW), so
            # resolution falls to the legacy engine → 0 refund pre-check-in.
            # The Property.cancellation_policy column and PropertyBookingPolicy row
            # do NOT drive the quote when the CancellationPolicy engine resolves.
            booking.policy_snapshot = {"cancellation_policy": "super_strict"}
            db.session.commit()
            booking_ref = booking.booking_reference
            guest_public_id = test_guest_user.public_id

        _login_as_guest(client, guest_public_id)

        with patch.object(MarketplaceService, 'refund_guest', return_value=(True, None)) as mock_refund:
            resp = client.post(
                f'/accommodation/guest/booking/{booking_ref}/cancel',
                data={'reason': 'Test cancellation'},
                follow_redirects=False
            )

            assert resp.status_code == 302
            # refund_guest should NOT be called when refund == 0
            mock_refund.assert_not_called()

    def test_cancel_failure_no_refund_called(self, app, client, test_db, test_property, test_guest_user, test_host_user, platform_org_id):
        """If cancel_booking fails (e.g., already cancelled), refund_guest NOT called."""
        with app.app_context():
            booking = _create_paid_booking(app, test_db, test_property, test_guest_user, test_host_user)
            # Pre-cancel it
            booking.status = AccommodationBookingStatus.CANCELLED.value
            db.session.commit()
            booking_ref = booking.booking_reference
            guest_public_id = test_guest_user.public_id

        _login_as_guest(client, guest_public_id)

        with patch.object(MarketplaceService, 'refund_guest', return_value=(True, None)) as mock_refund:
            resp = client.post(
                f'/accommodation/guest/booking/{booking_ref}/cancel',
                data={'reason': 'Test cancellation'},
                follow_redirects=False
            )

            # cancel_booking returns (False, msg, None) → no refund call
            assert resp.status_code == 302
            mock_refund.assert_not_called()


class TestHostRefundRoute:
    """Verify the existing host_refund_booking route still works (uses refund_guest correctly)."""

    def test_host_refund_uses_refund_guest(self, app, client, test_db, test_property, test_guest_user, test_host_user, platform_org_id):
        """Host refund route should call MarketplaceService.refund_guest."""
        with app.app_context():
            booking = _create_paid_booking(app, test_db, test_property, test_guest_user, test_host_user)
            booking_id = booking.id

        _login_as_host(client, test_host_user.public_id)

        # Mock _ensure_host_identity to return a valid host identity
        with patch('app.accommodation.routes._ensure_host_identity', return_value={"type": "individual", "id": test_host_user.id}):
            with patch.object(MarketplaceService, 'refund_guest', return_value=(True, None)) as mock_refund:
                resp = client.post(
                    f'/accommodation/host/booking/{booking_id}/refund',
                    data={'refund_amount': '100.00', 'reason': 'Partial refund'},
                    follow_redirects=False
                )

                assert resp.status_code == 302
                mock_refund.assert_called_once()
                args, kwargs = mock_refund.call_args
                assert args[0] == booking_id
                assert args[1] == Decimal("100.00")