"""
tests/wallet/test_withdraw_api.py
STAGE 6-2B.1 - F-19: Wallet withdraw API contract repair.

The endpoint ``/api/wallet/withdraw`` passed ``user_id=`` to
``WalletService.withdraw()``, whose contract takes ``account_id`` (Account
UUID). The kwarg mismatch raised ``TypeError`` -> HTTP 500 INTERNAL_ERROR on
every authenticated withdrawal.

These tests exercise the full HTTP path end-to-end (auth -> CSRF -> account
resolution -> service -> ledger) and prove the contract is repaired
caller-side without changing wallet architecture, ledger entries, idempotency
or ownership rules.
"""

import hashlib
import os
import uuid
from decimal import Decimal
from unittest.mock import patch

from itsdangerous import URLSafeTimedSerializer

from app.extensions import db
from app.identity.models.user import User
from app.wallet.models.ledger import AccountModel, LedgerEntryModel, EntryType
from app.wallet.models.transaction import TransactionModel, TransactionType, TransactionStatus
from app.wallet.repositories.account_repository import AccountRepository
from app.wallet.repositories.ledger_repository import LedgerRepository

# `app` comes from the central tests/conftest.py.


# ===========================================================================
# HELPERS
# ===========================================================================

def _make_user(app, tag):
    """Create a user, return (internal_id, public_id) as plain values."""
    with app.app_context():
        user = User(
            email=f'f19_{tag}_{uuid.uuid4().hex[:8]}@example.com',
            username=f'f19{tag}_{uuid.uuid4().hex[:8]}',
            password_hash='hashed',
            is_active=True,
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()
        return user.id, user.public_id


def _fund(app, user_id, currency='USD', amount=Decimal('1000')):
    """Create + fund a user account (mirrors the wallet test harness pattern).

    Returns the account UUID value so no detached ORM instance leaks.
    """
    from app.wallet.routes import get_or_create_account
    with app.app_context():
        account = get_or_create_account(user_id, currency)
        tx = TransactionModel(
            id=uuid.uuid4(),
            client_request_id=f'f19-fund-{uuid.uuid4()}',
            tx_type=TransactionType.DEPOSIT,
            amount=amount,
            currency=currency,
            status=TransactionStatus.COMPLETED,
            user_id=user_id,
        )
        db.session.add(tx)
        db.session.flush()
        db.session.add(LedgerEntryModel(
            transaction_id=tx.id,
            account_id=account.id,
            entry_type=EntryType.CREDIT,
            amount=amount,
            currency=currency,
        ))
        db.session.commit()
        return account.id


def _login_fresh_client(app, user_id, public_id):
    """Return a fresh test client logged in as ``user`` with a valid CSRF token.

    A fresh client is used per test because the root conftest ``client``
    fixture is session-scoped (cookies leak across tests).

    The signed CSRF token is produced with Flask-WTF's own serializer
    (``URLSafeTimedSerializer``, salt ``wtf-csrf-token``) over the raw token
    stored in the client's session, exactly as ``generate_csrf()`` does. We
    build it manually because ``client.session_transaction()`` does not push a
    request context (Flask 3.1), so ``flask.session``/``g`` are unavailable
    inside the transaction block.
    """
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(public_id)
        sess['_fresh'] = True
        raw = sess.get('csrf_token') or hashlib.sha1(os.urandom(64)).hexdigest()
        sess['csrf_token'] = raw
    with app.app_context():
        secret = app.config.get('WTF_CSRF_SECRET_KEY') or app.secret_key
        token = URLSafeTimedSerializer(secret, salt='wtf-csrf-token').dumps(raw)
    return client, token


def _post(client, csrf_token, path='/api/wallet/withdraw', idempotency_key=None, **kwargs):
    headers = kwargs.pop('headers', {})
    headers.setdefault('X-CSRF-Token', csrf_token)
    headers.setdefault('X-Idempotency-Key', idempotency_key or f'f19-{uuid.uuid4()}')
    return client.post(path, headers=headers, **kwargs)


def _allow_kyc():
    return patch(
        'app.wallet.services.kyc_limit_service.KYCLimitService.check_transaction_allowed',
        return_value={'allowed': True, 'kyc_level': 4},
    )


def _debit_count(app, account_id):
    with app.app_context():
        return db.session.query(LedgerEntryModel).filter_by(
            account_id=account_id, entry_type=EntryType.DEBIT
        ).count()


# ===========================================================================
# F-19 CONTRACT TESTS
# ===========================================================================

class TestWithdrawApiContract:

    def test_happy_path_withdraw_via_api(self, app):
        user_id, public_id = _make_user(app, 'happy')
        account_uuid = _fund(app, user_id, 'USD', Decimal('1000'))
        client, csrf = _login_fresh_client(app, user_id, public_id)
        key = f'f19-happy-{uuid.uuid4()}'

        with _allow_kyc():
            resp = _post(client, csrf, idempotency_key=key, json={
                'amount': '50.00',
                'currency': 'USD',
                'destination_type': 'mobile_money',
                'destination_details': {'phone': '256700000000', 'provider': 'mtn'},
            })

        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()['data']
        assert data['amount'] == '50.00'
        assert data['currency'] == 'USD'
        assert Decimal(data['new_balance']) == Decimal('950.00')
        assert data['status'] == 'success'
        assert data['account_id'] == str(account_uuid)

        # Ledger + transaction integrity
        with app.app_context():
            assert LedgerRepository().get_balance(account_uuid, 'USD') == Decimal('950.00')
            assert _debit_count(app, account_uuid) == 1
            tx = db.session.query(TransactionModel).filter_by(client_request_id=key).one()
            assert tx.tx_type == TransactionType.WITHDRAW
            assert tx.status == TransactionStatus.COMPLETED
            assert tx.amount == Decimal('50.00')
            assert tx.user_id == user_id

    def test_withdraw_requires_login(self, app):
        client = app.test_client()
        resp = client.post('/api/wallet/withdraw',
                           headers={'X-Idempotency-Key': 'f19-anon'},
                           json={'amount': '10', 'currency': 'USD'})
        assert resp.status_code in (302, 401, 403)
        assert resp.status_code != 500

    def test_withdraw_requires_csrf_token(self, app):
        user_id, public_id = _make_user(app, 'csrf')
        _fund(app, user_id)
        client, _csrf = _login_fresh_client(app, user_id, public_id)
        resp = client.post('/api/wallet/withdraw',
                           headers={'X-Idempotency-Key': 'f19-csrf'},
                           json={'amount': '10', 'currency': 'USD'})
        assert resp.status_code == 403
        assert resp.get_json()['code'] == 'CSRF_TOKEN_REQUIRED'

    def test_withdraw_without_account_returns_404(self, app):
        user_id, public_id = _make_user(app, 'noacct')
        client, csrf = _login_fresh_client(app, user_id, public_id)
        with _allow_kyc():
            resp = _post(client, csrf, json={'amount': '10', 'currency': 'USD'})
        assert resp.status_code == 404
        assert resp.get_json()['code'] == 'WALLET_NOT_FOUND'

    def test_withdraw_wrong_currency_returns_404(self, app):
        user_id, public_id = _make_user(app, 'cur')
        _fund(app, user_id, 'USD', Decimal('1000'))
        client, csrf = _login_fresh_client(app, user_id, public_id)
        with _allow_kyc():
            resp = _post(client, csrf, json={'amount': '10', 'currency': 'UGX'})
        assert resp.status_code == 404
        assert resp.get_json()['code'] == 'WALLET_NOT_FOUND'

    def test_withdraw_insufficient_balance_returns_402(self, app):
        user_id, public_id = _make_user(app, 'poor')
        _fund(app, user_id, 'USD', Decimal('100'))
        client, csrf = _login_fresh_client(app, user_id, public_id)
        with _allow_kyc():
            resp = _post(client, csrf, json={'amount': '500', 'currency': 'USD'})
        assert resp.status_code == 402
        assert resp.get_json()['code'] == 'INSUFFICIENT_BALANCE'

    def test_withdraw_invalid_amount_returns_400(self, app):
        user_id, public_id = _make_user(app, 'badamt')
        _fund(app, user_id)
        client, csrf = _login_fresh_client(app, user_id, public_id)
        resp = _post(client, csrf, json={'amount': '0', 'currency': 'USD'})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'VALIDATION_ERROR'

    def test_withdraw_frozen_account_returns_403(self, app):
        user_id, public_id = _make_user(app, 'frozen')
        account_uuid = _fund(app, user_id, 'USD', Decimal('1000'))
        with app.app_context():
            acc = db.session.get(AccountModel, account_uuid)
            acc.is_frozen = True
            acc.frozen_reason = 'F-19 test freeze'
            db.session.commit()
        client, csrf = _login_fresh_client(app, user_id, public_id)
        with _allow_kyc():
            resp = _post(client, csrf, json={'amount': '10', 'currency': 'USD'})
        assert resp.status_code == 403
        assert resp.get_json()['code'] == 'WALLET_FROZEN'

    def test_withdraw_is_idempotent(self, app):
        user_id, public_id = _make_user(app, 'idem')
        account_uuid = _fund(app, user_id, 'USD', Decimal('1000'))
        client, csrf = _login_fresh_client(app, user_id, public_id)
        key = f'f19-idem-{uuid.uuid4()}'

        with _allow_kyc():
            r1 = _post(client, csrf, idempotency_key=key,
                       json={'amount': '50', 'currency': 'USD'})
            r2 = _post(client, csrf, idempotency_key=key,
                       json={'amount': '50', 'currency': 'USD'})

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert Decimal(r1.get_json()['data']['new_balance']) == Decimal('950.00')
        assert r2.get_json()['data'].get('already_processed') is True
        assert _debit_count(app, account_uuid) == 1
        with app.app_context():
            assert LedgerRepository().get_balance(account_uuid, 'USD') == Decimal('950.00')

    def test_withdraw_authz_debits_only_own_account(self, app):
        user_a_id, user_a_pid = _make_user(app, 'authz_a')
        user_b_id, _user_b_pid = _make_user(app, 'authz_b')
        account_a_uuid = _fund(app, user_a_id, 'USD', Decimal('1000'))
        account_b_uuid = _fund(app, user_b_id, 'USD', Decimal('1000'))
        client, csrf = _login_fresh_client(app, user_a_id, user_a_pid)

        with _allow_kyc():
            resp = _post(client, csrf, json={'amount': '50', 'currency': 'USD'})

        assert resp.status_code == 200
        assert resp.get_json()['data']['account_id'] == str(account_a_uuid)
        with app.app_context():
            assert LedgerRepository().get_balance(account_a_uuid, 'USD') == Decimal('950.00')
            assert LedgerRepository().get_balance(account_b_uuid, 'USD') == Decimal('1000.00')
            assert _debit_count(app, account_a_uuid) == 1
            assert _debit_count(app, account_b_uuid) == 0

    def test_withdraw_response_never_exposes_internal_user_id(self, app):
        user_id, public_id = _make_user(app, 'dualid')
        _fund(app, user_id, 'USD', Decimal('1000'))
        client, csrf = _login_fresh_client(app, user_id, public_id)
        with _allow_kyc():
            resp = _post(client, csrf, json={'amount': '10', 'currency': 'USD'})
        assert resp.status_code == 200
        assert str(user_id) not in resp.get_data(as_text=True)
        assert {'status', 'data'} >= set(resp.get_json().keys())
        assert 'user_id' not in resp.get_json()['data']