"""
F-03c — WalletService._is_admin() authorization fix
====================================================
Defect: wallet_service.py:75 calls current_user.has_role(role) but User has
no has_role method (only has_global_role / role_names). Every authenticated
non-owner user triggers AttributeError -> platform-account refund/payout
transfers are dead in production.

Fix: replace has_role -> has_global_role (context-aware, respects active role).
Also fix admin_api.py:34 (same broken pattern).

Tests: RED before fix (AttributeError / wrong behavior), GREEN after.
"""

import uuid
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.identity.models.user import User, UserRole
from app.identity.models.roles_permission import Role
from app.wallet.models.ledger import AccountModel
from app.wallet.models.transaction import TransactionModel, TransactionType, TransactionStatus
from app.wallet.models.ledger import LedgerEntryModel, EntryType
from app.wallet.services.wallet_service import WalletService
from app.wallet.api.admin_api import require_any_role


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
# `app` comes from the central tests/conftest.py (session-scoped, config
# restored per test). The `user`/`other_user`/`admin_user`/`wallet_service`
# fixtures below create real rows inside the shared isolation lifecycle.

@pytest.fixture
def user(app):
    """Create a plain user with no special roles."""
    tag = uuid.uuid4().hex[:8]
    u = User(
        username=f'f03c_plain_{tag}',
        email=f'f03c_plain_{tag}@test.com',
        first_name='Test',
        last_name='User',
    )
    u.set_password('pass')
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def other_user(app):
    """Create a second plain user (for non-owner transfer tests)."""
    tag = uuid.uuid4().hex[:8]
    u = User(
        username=f'f03c_other_{tag}',
        email=f'f03c_other_{tag}@test.com',
        first_name='Other',
        last_name='User',
    )
    u.set_password('pass')
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def admin_user(app):
    """Create a user with super_admin role."""
    tag = uuid.uuid4().hex[:8]
    role = Role.query.filter_by(name='super_admin').first()
    if not role:
        role = Role(name='super_admin', description='Super Admin')
        db.session.add(role)
        db.session.commit()
    u = User(
        username=f'f03c_admin_{tag}',
        email=f'f03c_admin_{tag}@test.com',
        first_name='Admin',
        last_name='User',
    )
    u.set_password('pass')
    db.session.add(u)
    db.session.commit()
    ur = UserRole(user_id=u.id, role_id=role.id)
    db.session.add(ur)
    db.session.commit()
    return u


@pytest.fixture
def wallet_service(app):
    return WalletService(db.session)


# ---------------------------------------------------------------------------
# Tests: _is_admin() direct behavior
# ---------------------------------------------------------------------------

class TestIsAdminBehavior:
    """Verify _is_admin returns correct results for different user types.

    Uses mocked current_user in wallet_service module to avoid conftest
    request context interference.
    """

    def test_unauthenticated_user_returns_false(self, app, wallet_service):
        """_is_admin must return False when no user is logged in."""
        with patch('app.wallet.services.wallet_service.current_user') as mock_user:
            mock_user.is_authenticated = False
            assert wallet_service._is_admin() is False

    def test_plain_user_returns_false(self, app, wallet_service):
        """_is_admin must return False for a user with no admin roles."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.has_global_role.return_value = False

        with patch('app.wallet.services.wallet_service.current_user', mock_user):
            result = wallet_service._is_admin()
            assert result is False, (
                f"_is_admin() should return False for plain user, got {result}"
            )

    def test_admin_user_returns_true(self, app, wallet_service):
        """_is_admin must return True for a user with super_admin role."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.has_global_role.side_effect = lambda *roles: 'super_admin' in roles

        with patch('app.wallet.services.wallet_service.current_user', mock_user):
            result = wallet_service._is_admin()
            assert result is True, (
                f"_is_admin() should return True for super_admin user, got {result}"
            )


# ---------------------------------------------------------------------------
# Tests: transfer ownership gate
# ---------------------------------------------------------------------------

def _fund_account(app, account_id, amount=Decimal('5000'), currency='UGX'):
    """Fund an account directly (no wallet_service dependency)."""
    from app.wallet.models.transaction import TransactionModel, TransactionType, TransactionStatus
    from app.wallet.models.ledger import LedgerEntryModel, EntryType
    tx = TransactionModel(
        id=uuid.uuid4(),
        client_request_id=f'f03c-fund-{uuid.uuid4().hex[:8]}',
        tx_type=TransactionType.DEPOSIT,
        amount=amount,
        currency=currency,
        status=TransactionStatus.COMPLETED,
        user_id=None,
    )
    db.session.add(tx)
    db.session.flush()
    db.session.add(LedgerEntryModel(
        transaction_id=tx.id,
        account_id=account_id,
        entry_type=EntryType.CREDIT,
        amount=amount,
        currency=currency,
    ))
    db.session.commit()


class TestTransferOwnershipGate:
    """Verify transfer rejects non-owner transfers without admin role.

    Uses _is_admin integration test: patches _is_admin and KYC to control
    the gates and verifies the ownership check in transfer() responds correctly.
    """

    def test_non_owner_transfer_rejected_when_not_admin(self, app, user, other_user, wallet_service):
        """transfer must reject when from_account.user_id != current_user.id
        and _is_admin() returns False."""
        acc_from = AccountModel(
            user_id=other_user.id,
            currency='UGX',
            owner_type='user',
            account_type='wallet',
        )
        acc_to = AccountModel(
            user_id=user.id,
            currency='UGX',
            owner_type='user',
            account_type='wallet',
        )
        db.session.add_all([acc_from, acc_to])
        db.session.commit()

        # Fund the from_account
        _fund_account(app, acc_from.id)

        # Mock current_user in wallet_service module to avoid conftest context issues
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = user.id

        with app.test_request_context():
            with patch('app.wallet.services.wallet_service.current_user', mock_user):
                with patch.object(wallet_service, '_is_admin', return_value=False):
                    with patch.object(wallet_service, '_check_kyc_limits'):
                        with pytest.raises(PermissionError, match="do not have permission"):
                            wallet_service.transfer(
                                from_account_id=str(acc_from.id),
                                to_account_id=str(acc_to.id),
                                amount=Decimal('1000'),
                                currency='UGX',
                                client_request_id=f'f03c-rej-{uuid.uuid4().hex[:8]}',
                            )

    def test_system_initiated_skips_ownership_check(self, app, user, other_user, wallet_service):
        """transfer with system_initiated=True skips ownership check entirely."""
        acc_from = AccountModel(
            user_id=other_user.id,
            currency='UGX',
            owner_type='user',
            account_type='wallet',
        )
        acc_to = AccountModel(
            user_id=user.id,
            currency='UGX',
            owner_type='user',
            account_type='wallet',
        )
        db.session.add_all([acc_from, acc_to])
        db.session.commit()

        # Fund the from_account
        _fund_account(app, acc_from.id)

        # Mock current_user in wallet_service module
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = user.id

        with app.test_request_context():
            with patch('app.wallet.services.wallet_service.current_user', mock_user):
                with patch.object(wallet_service, '_check_kyc_limits'):
                    try:
                        wallet_service.transfer(
                            from_account_id=str(acc_from.id),
                            to_account_id=str(acc_to.id),
                            amount=Decimal('1000'),
                            currency='UGX',
                            client_request_id=f'f03c-sys-{uuid.uuid4().hex[:8]}',
                            system_initiated=True,
                        )
                    except PermissionError:
                        pytest.fail("system_initiated transfer should not raise PermissionError")


# ---------------------------------------------------------------------------
# Tests: admin_api.py require_any_role decorator
# ---------------------------------------------------------------------------

class TestAdminApiRoleDecorator:
    """Verify admin_api.py require_any_role works with has_global_role.

    Uses mock current_user to avoid conftest autouse request context
    interference with login_user.
    """

    def _make_protected(self):
        """Create a decorated function without Flask route registration."""
        @require_any_role('super_admin', 'admin')
        def protected():
            return 'ok'
        return protected

    def test_require_any_role_rejects_unauthorized(self, app):
        """require_any_role must return 403 for user without required role."""
        protected = self._make_protected()
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.has_global_role.return_value = False

        with patch('app.wallet.api.admin_api.current_user', mock_user):
            result = protected()
            assert isinstance(result, tuple)
            assert result[1] == 403

    def test_require_any_role_allows_authorized(self, app):
        """require_any_role must allow user with required role."""
        protected = self._make_protected()
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.has_global_role.side_effect = lambda *roles: 'super_admin' in roles

        with patch('app.wallet.api.admin_api.current_user', mock_user):
            result = protected()
            assert result == 'ok'

    def test_require_any_role_rejects_unauthenticated(self, app):
        """require_any_role must return 401 for unauthenticated user."""
        protected = self._make_protected()
        mock_user = MagicMock()
        mock_user.is_authenticated = False

        with patch('app.wallet.api.admin_api.current_user', mock_user):
            result = protected()
            assert isinstance(result, tuple)
            assert result[1] == 401
