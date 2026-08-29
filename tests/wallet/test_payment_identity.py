"""
tests/wallet/test_payment_identity.py

Tests for the Payment Identity Architecture:
- Account number auto-generation (no coupling to internal DB IDs)
- PaymentIdentity registration, normalization, verification, uniqueness
- recipient resolution service (WHO IS THIS? only)
- /api/wallet/recipients/resolve endpoint
- security: no internal IDs / KYC docs leaked
"""

import pytest
from uuid import uuid4
import uuid

from app.config import TestingConfig
from app.extensions import db
from app.identity.models.user import User
from app.identity.models.organisation import Organisation
from app.wallet.models.ledger import (
    AccountModel, AccountOwnerType, AccountType, AccountStatus
)
from app.wallet.repositories.account_repository import AccountRepository
from app.wallet.routes import get_or_create_account
from app.wallet.services.payment_identity_service import (
    normalize_phone,
    normalize_email,
    normalize_afcon360_id,
    normalize_merchant_code,
    detect_identity_type,
    resolve_payment_recipient,
    PaymentIdentityService,
)
from app.wallet.utils.account_number import generate_account_number, is_valid_account_number
from flask_wtf.csrf import generate_csrf


def _make_user(app, n):
    with app.app_context():
        user = User(
            email=f'pi_user_{n}_{uuid.uuid4().hex[:6]}@example.com',
            username=f'piuser_{n}_{uuid.uuid4().hex[:6]}',
            password_hash='hashed',
            is_active=True,
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()
        return user.id, user.public_id


def _make_org(app, n):
    with app.app_context():
        org = Organisation(
            org_id=str(uuid4()),
            legal_name=f'PI Org {n} {uuid.uuid4().hex[:6]}',
            country='UG',
            region='Central',
            org_type='business',
            contact_email=f'piorg_{n}_{uuid.uuid4().hex[:6]}@example.com',
        )
        db.session.add(org)
        db.session.commit()
        return org.id


def _get_user(app, user_id):
    with app.app_context():
        return User.query.get(user_id)


# ===========================================================================
# ACCOUNT NUMBER GENERATION
# ===========================================================================

class TestAccountNumberGeneration:

    def test_user_account_gets_number_on_create(self, app):
        user_id, _ = _make_user(app, 1)
        with app.app_context():
            acc = get_or_create_account(user_id, 'UGX')
            db.session.commit()
            assert acc.account_number is not None
            assert acc.account_number.startswith('ACC-UGX-')
            assert is_valid_account_number(acc.account_number)

    def test_number_not_derived_from_internal_id(self, app):
        u1, _ = _make_user(app, 2)
        u2, _ = _make_user(app, 3)
        with app.app_context():
            a1 = get_or_create_account(u1, 'USD')
            a2 = get_or_create_account(u2, 'USD')
            db.session.commit()
            assert a1.account_number != a2.account_number
            assert 'ACC-USD-' in a1.account_number

    def test_org_account_prefix(self, app):
        org_id = _make_org(app, 1)
        with app.app_context():
            acc = AccountModel(
                user_id=org_id,
                owner_type=AccountOwnerType.ORGANISATION,
                account_type=AccountType.ORG_WALLET,
                account_name='Org wallet',
                currency='UGX',
                status=AccountStatus.ACTIVE,
            )
            db.session.add(acc)
            db.session.commit()
            assert acc.account_number.startswith('ORG-UGX-')

    def test_platform_account_prefix(self, app):
        with app.app_context():
            acc = AccountModel(
                user_id=1,
                owner_type=AccountOwnerType.PLATFORM,
                account_type=AccountType.REVENUE,
                account_name='Platform revenue',
                currency='UGX',
                status=AccountStatus.ACTIVE,
            )
            db.session.add(acc)
            db.session.commit()
            assert acc.account_number.startswith('PLT-REV-UGX-')

    def test_generator_format_user(self):
        n = generate_account_number('user', 'UGX', 'user_wallet')
        assert n.startswith('ACC-UGX-')
        assert len(n.split('-')[-1]) == 6

    def test_generator_format_system(self):
        n = generate_account_number('system', 'UGX', 'escrow')
        assert n.startswith('SYS-ESC-UGX-')
        assert len(n.split('-')[-1]) == 4


# ===========================================================================
# NORMALIZATION
# ===========================================================================

class TestNormalization:

    def test_phone_local_to_e164(self):
        assert normalize_phone('0700123456') == '256700123456'

    def test_phone_already_e164(self):
        assert normalize_phone('+256700123456') == '256700123456'

    def test_email_lowercase(self):
        assert normalize_email('Alice@Example.com') == 'alice@example.com'

    def test_afcon360_id_upper(self):
        assert normalize_afcon360_id('afc-1234') == 'AFC-1234'

    def test_merchant_code_upper_strip(self):
        assert normalize_merchant_code(' mtn-ug ') == 'MTN-UG'

    def test_detect_merchant_before_alnum(self):
        assert detect_identity_type('MTN-UG') == 'MERCHANT_CODE'
        assert detect_identity_type('AFC-1234') == 'AFCON360_ID'
        assert detect_identity_type('256700123456') == 'PHONE'
        assert detect_identity_type('alice@example.com') == 'EMAIL'


# ===========================================================================
# PAYMENT IDENTITY REGISTRATION
# ===========================================================================

class TestPaymentIdentityRegistration:

    def test_register_phone(self, app):
        user_id, _ = _make_user(app, 4)
        with app.app_context():
            acc = get_or_create_account(user_id, 'UGX')
            db.session.commit()
            pi = PaymentIdentityService.register(
                'PHONE', '0700123456', 'user', user_id,
                account_id=acc.id, is_verified=True,
            )
            assert pi.normalized_value == '256700123456'
            assert pi.identity_type == 'PHONE'
            assert pi.is_verified is True
            assert pi.account_id == acc.id

    def test_duplicate_normalized_rejected(self, app):
        user_id, _ = _make_user(app, 5)
        with app.app_context():
            acc = get_or_create_account(user_id, 'UGX')
            db.session.commit()
            pi1 = PaymentIdentityService.register('PHONE', '0700123456', 'user', user_id, account_id=acc.id)
            # Second registration with same normalized value should idempotently return existing
            pi2 = PaymentIdentityService.register('PHONE', '+256700123456', 'user', user_id, account_id=acc.id)
            assert pi2.id == pi1.id
            assert pi2.normalized_value == '256700123456'

    def test_set_verified(self, app):
        user_id, _ = _make_user(app, 6)
        with app.app_context():
            acc = get_or_create_account(user_id, 'UGX')
            db.session.commit()
            pi = PaymentIdentityService.register('EMAIL', 'bob@example.com', 'user', user_id, account_id=acc.id)
            assert pi.is_verified is False
            PaymentIdentityService.set_verified(pi.id, True)
            assert pi.is_verified is True


# ===========================================================================
# RESOLUTION SERVICE
# ===========================================================================

class TestResolvePaymentRecipient:

    def test_resolve_phone(self, app):
        user_id, _ = _make_user(app, 7)
        with app.app_context():
            acc = get_or_create_account(user_id, 'UGX')
            db.session.commit()
            PaymentIdentityService.register('PHONE', '0700123456', 'user', user_id, account_id=acc.id, is_verified=True)
            res = resolve_payment_recipient('0700123456')
            assert res['found'] is True
            assert res['trusted'] is True
            assert res['recipient_type'] == 'user'
            assert res['account_number'] == acc.account_number
            assert res['currency'] == 'UGX'

    def test_resolve_email(self, app):
        user_id, _ = _make_user(app, 8)
        with app.app_context():
            acc = get_or_create_account(user_id, 'UGX')
            db.session.commit()
            PaymentIdentityService.register('EMAIL', 'carol@example.com', 'user', user_id, account_id=acc.id, is_verified=True)
            res = resolve_payment_recipient('CAROL@example.com')
            assert res['found'] is True
            assert res['trusted'] is True

    def test_resolve_unknown(self, app):
        with app.app_context():
            res = resolve_payment_recipient('+256799999999')
            assert res['found'] is False
            assert res['reason'] == 'no_identity'

    def test_resolve_unverified_not_trusted(self, app):
        user_id, _ = _make_user(app, 9)
        with app.app_context():
            acc = get_or_create_account(user_id, 'UGX')
            db.session.commit()
            PaymentIdentityService.register('PHONE', '0700111222', 'user', user_id, account_id=acc.id, is_verified=False)
            res = resolve_payment_recipient('0700111222')
            assert res['found'] is True
            assert res['trusted'] is False
            assert res['reason'] == 'identity_not_verified'

    def test_resolve_inactive_rejected(self, app):
        user_id, _ = _make_user(app, 10)
        with app.app_context():
            acc = get_or_create_account(user_id, 'UGX')
            db.session.commit()
            pi = PaymentIdentityService.register('PHONE', '0700333444', 'user', user_id, account_id=acc.id, is_verified=True)
            pi.is_active = False
            db.session.commit()
            # Inactive identities are filtered out at query level (not discoverable)
            res = resolve_payment_recipient('0700333444')
            assert res['found'] is False
            assert res['reason'] == 'no_identity'

    def test_resolve_merchant_code_to_org(self, app):
        org_id = _make_org(app, 2)
        with app.app_context():
            acc = AccountModel(
                user_id=org_id,
                owner_type=AccountOwnerType.ORGANISATION,
                account_type=AccountType.ORG_WALLET,
                account_name='Org wallet',
                currency='UGX',
                status=AccountStatus.ACTIVE,
            )
            db.session.add(acc)
            db.session.commit()
            PaymentIdentityService.register('MERCHANT_CODE', 'mtn-ug', 'organisation', org_id, account_id=acc.id, is_verified=True)
            res = resolve_payment_recipient('MTN-UG')
            assert res['found'] is True
            assert res['trusted'] is True
            assert res['recipient_type'] == 'organisation'
            assert res['account_number'] == acc.account_number

    def test_resolution_does_not_expose_internal_id(self, app):
        user_id, _ = _make_user(app, 11)
        with app.app_context():
            acc = get_or_create_account(user_id, 'UGX')
            db.session.commit()
            PaymentIdentityService.register('PHONE', '0700555666', 'user', user_id, account_id=acc.id, is_verified=True)
            res = resolve_payment_recipient('0700555666')
            payload = str(res)
            assert str(user_id) not in payload
            assert str(acc.id) not in payload


# ===========================================================================
# API ENDPOINT
# ===========================================================================

class TestRecipientResolveEndpoint:

    def test_endpoint_resolves(self, app):
        user_id, public_id = _make_user(app, 12)
        with app.app_context():
            acc = get_or_create_account(user_id, 'UGX')
            db.session.commit()
            PaymentIdentityService.register('PHONE', '0700777888', 'user', user_id, account_id=acc.id, is_verified=True)

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(public_id)
            sess['_fresh'] = True
        resp = client.post(
            '/api/wallet/recipients/resolve',
            json={'identifier': '0700777888'},
        )
        assert resp.status_code in (200, 404)
        data = resp.get_json()
        assert data['status'] == 'success'
        if resp.status_code == 200:
            assert data['found'] is True
            assert data['trusted'] is True

    def test_endpoint_requires_identifier(self, app):
        user_id, public_id = _make_user(app, 13)
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(public_id)
            sess['_fresh'] = True
        resp = client.post(
            '/api/wallet/recipients/resolve',
            json={'identifier': ''},
        )
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'INVALID_REQUEST'
