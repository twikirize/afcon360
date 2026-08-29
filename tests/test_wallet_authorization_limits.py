"""
Authoritative KYC/wallet authorization boundary tests.

These tests pin the agreed architecture (Decision 1 = Option A, Decision 2):

- Regulatory KYC daily/monthly limits are CUMULATIVE, owned by KYC, and enforced
  for ALL wallet entry points inside WalletService using ledger-derived volume as
  the single authoritative source.
- WalletSystemConfig max_deposit/withdraw/transfer amounts are OPERATIONAL
  per-transaction ceilings only (NOT daily/monthly ceilings).
- AML/FIA authority lives in kyc_config_schema.get_thresholds(); WalletSystemConfig
  .aml_threshold is dead and must never become a competing threshold.
- Individual tier authority = calculate_kyc_tier (documents); User.kyc_level is a
  denormalized cache only. Org authority = OrganisationKYBService.compute_status.
- Authorization helpers MUST fail closed and MUST NOT commit transactions.

Wallets to keep green after production hardening.
"""

import pytest
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
from decimal import Decimal
from datetime import datetime, timezone

from app.auth.kyc_compliance import (
    calculate_kyc_tier,
    TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD, TIER_3_ENHANCED, TIER_4_PREMIUM,
)
from app.wallet.services.kyc_limit_service import KYCLimitService, LimitExceededError
from app.wallet.services.wallet_service import WalletService


def cta(*args, **kwargs):
    """Wrapper: KYCLimitService.check_transaction_allowed returns a Dict, not a tuple."""
    r = KYCLimitService.check_transaction_allowed(*args, **kwargs)
    return r.get('allowed', False), r.get('reason', '')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tier_info(tier, txn, daily=0, monthly=0):
    return {
        "tier": tier,
        "tier_name": f"T{tier}",
        "limits": {"daily": daily, "monthly": monthly, "transaction": txn},
        "can_deposit": True,
        "can_withdraw": True,
        "can_transfer": True,
    }


def make_config(deposit=1_000_000, withdrawal=500_000, transfer=1_000_000):
    c = MagicMock()
    c.max_deposit_amount = deposit
    c.max_withdrawal_amount = withdrawal
    c.max_transfer_amount = transfer
    return c


def _org_mock(pk):
    """MagicMock Organisation that survives OrganisationKYBService helper attribute access."""
    m = MagicMock(id=pk)
    m.is_deleted = False
    m.get_setting = lambda key, default=None: default
    return m


@contextmanager
def calc_kyc_patches():
    """Patch calculate_kyc_tier's collaborators so the REAL function runs."""
    with patch('app.auth.kyc_compliance.is_requirement_enabled', return_value=True), \
         patch('app.kyc.models.KycRecord') as MockKycRecord, \
         patch('app.auth.kyc_compliance.db') as mock_db, \
         patch('app.auth.kyc_compliance.get_profile_by_user', return_value=None), \
         patch('app.auth.kyc_compliance.IndividualVerification') as MockVerification:
        mock_user = MagicMock()
        mock_user.public_id = 'pub'
        mock_user.phone_verified = True
        mock_user.phone_verified_at = datetime.now(timezone.utc)
        mock_user.phone = '+256700000000'
        mock_db.session.get.return_value = mock_user
        MockKycRecord.query.filter_by.return_value.order_by.return_value.first.return_value = None
        MockKycRecord.query.filter_by.return_value.all.return_value = []
        yield mock_user, MockVerification, MockKycRecord


@contextmanager
def kyc_limit_patches(tier=None, txn=None, daily=None, monthly=None,
                      config=None, org_status=None):
    """Patch KYCLimitService collaborators for service-level tests."""
    from app.identity.models.organisation import Organisation

    def _get(cls, pk):
        if org_status is not None and cls is Organisation:
            return _org_mock(pk)
        return None

    calc = patch('app.auth.kyc_compliance.calculate_kyc_tier',
                 return_value=tier_info(tier if tier is not None else TIER_2_STANDARD,
                                        txn if txn is not None else 500000,
                                        daily if daily is not None else 0,
                                        monthly if monthly is not None else 0))
    if org_status is not None:
        cs = patch('app.identity.services.organisation_kyb_service.OrganisationKYBService.compute_status',
                   return_value=org_status)
    else:
        cs = patch('app.identity.services.organisation_kyb_service.OrganisationKYBService.compute_status')

    with calc, \
         patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config',
               return_value=config or make_config()), \
         patch('app.wallet.services.kyc_limit_service.db.session.get', side_effect=_get), \
         cs:
        yield


# ---------------------------------------------------------------------------
# INDIVIDUAL TIER AUTHORITY (1-8)
# ---------------------------------------------------------------------------

class TestIndividualTierAuthority:
    def test_tier0_cannot_perform_restricted_transaction(self, app):
        with app.app_context():
            with kyc_limit_patches(tier=TIER_0_UNREGISTERED, txn=0, config=make_config()):
                allowed, reason = cta(1, Decimal('1000'), 'send')
                assert allowed is False
                assert 'not permitted' in reason.lower() or 'tier' in reason.lower()

    def test_tier1_limits_enforced(self, app):
        with app.app_context():
            with kyc_limit_patches(tier=TIER_1_BASIC, txn=100000, config=make_config()):
                denied, _ = cta(1, Decimal('150000'), 'deposit')
                allowed, _ = cta(1, Decimal('50000'), 'deposit')
                assert denied is False
                assert allowed is True

    def test_per_transaction_clamped_to_operational_ceiling(self, app):
        # Per-transaction deposit = min(regulatory per-txn, operational max_deposit_amount).
        with app.app_context():
            with kyc_limit_patches(tier=TIER_2_STANDARD, config=make_config()):
                # operational max_deposit = 1_000_000, regulatory per-txn = 500_000 -> ceiling 500k
                assert cta(1, Decimal('400000'), 'deposit')[0] is True
                assert cta(1, Decimal('600000'), 'deposit')[0] is False
            with kyc_limit_patches(tier=TIER_3_ENHANCED, config=make_config(deposit=50_000_000)):
                # operational max_deposit = 50M, regulatory per-txn = 2M -> ceiling 2M
                assert cta(1, Decimal('1500000'), 'deposit')[0] is True
                assert cta(1, Decimal('2500000'), 'deposit')[0] is False

    def test_expired_kyc_override_does_not_increase_tier(self, app):
        with calc_kyc_patches() as (mock_user, MockVerification, MockKycRecord):
            MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = None
            rec = MagicMock()
            rec.status = 'verified'
            rec.expiry_date = datetime(2000, 1, 1, tzinfo=timezone.utc)  # expired
            MockKycRecord.query.filter_by.return_value.order_by.return_value.first.return_value = rec
            MockKycRecord.query.filter_by.return_value.all.return_value = [rec]
            result = calculate_kyc_tier(1)
            assert result["tier"] == TIER_1_BASIC  # expired override ignored, phone-only

    def test_revoked_kyc_lower_tier(self, app):
        with calc_kyc_patches() as (mock_user, MockVerification, MockKycRecord):
            MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = None
            rec = MagicMock()
            rec.status = 'rejected'  # valid but rejected
            rec.expiry_date = datetime(2099, 1, 1, tzinfo=timezone.utc)
            MockKycRecord.query.filter_by.return_value.order_by.return_value.first.return_value = rec
            result = calculate_kyc_tier(1)
            assert result["tier"] == TIER_1_BASIC  # not elevated

    def test_pending_kyc_does_not_receive_approved_tier(self, app):
        with calc_kyc_patches() as (mock_user, MockVerification, MockKycRecord):
            mv = MagicMock()
            mv.status = 'pending'  # not verified/approved
            mv.scope = {"national_id": True, "biometric": True}
            MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = mv
            result = calculate_kyc_tier(1)
            assert result["tier"] == TIER_1_BASIC

    def test_resubmission_recalculates(self, app):
        from app.auth.kyc_compliance import clear_kyc_tier_cache
        with calc_kyc_patches() as (mock_user, MockVerification, MockKycRecord):
            # First: no verification -> tier 1 (phone)
            MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = None
            assert calculate_kyc_tier(1)["tier"] == TIER_1_BASIC
            # Clear cache to force recalculation
            clear_kyc_tier_cache(1)
            # Then: verified document -> tier 2
            mv = MagicMock()
            mv.status = 'verified'
            mv.scope = {"national_id": True, "biometric": True}
            MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = mv
            assert calculate_kyc_tier(1)["tier"] == TIER_2_STANDARD

    def test_static_user_kyc_level_not_authority(self, app):
        # check_transaction_allowed derives tier from calculate_kyc_tier, not User.kyc_level
        with app.app_context():
            with kyc_limit_patches(tier=TIER_1_BASIC, txn=100000, config=make_config()):
                assert cta(1, Decimal('150000'), 'deposit')[0] is False  # tier1 strict
                assert cta(1, Decimal('50000'), 'deposit')[0] is True


# ---------------------------------------------------------------------------
# PER-TRANSACTION PRECEDENCE: regulatory MIN(operational) (9-13)
# ---------------------------------------------------------------------------

class TestPerTransactionPrecedence:
    def test_regulatory_lower_than_operational(self, app):
        with app.app_context():
            with kyc_limit_patches(tier=TIER_1_BASIC, txn=100000, config=make_config(deposit=1_000_000)):
                assert cta(1, Decimal('150000'), 'deposit')[0] is False
                assert cta(1, Decimal('50000'), 'deposit')[0] is True

    def test_operational_lower_than_regulatory(self, app):
        with app.app_context():
            with kyc_limit_patches(tier=TIER_4_PREMIUM, txn=5_000_000, config=make_config(withdrawal=500_000)):
                assert cta(1, Decimal('600000'), 'withdraw')[0] is False
                assert cta(1, Decimal('400000'), 'withdraw')[0] is True

    def test_deposit_uses_max_deposit_amount(self, app):
        with app.app_context():
            with kyc_limit_patches(tier=TIER_4_PREMIUM, txn=5_000_000,
                                   config=make_config(deposit=2_000_000, transfer=1_000_000)):
                assert cta(1, Decimal('2500000'), 'deposit')[0] is False
                assert cta(1, Decimal('1500000'), 'deposit')[0] is True
                # transfer uses a different (lower) ceiling
                assert cta(1, Decimal('1500000'), 'send')[0] is False

    def test_withdrawal_uses_max_withdrawal_amount(self, app):
        with app.app_context():
            with kyc_limit_patches(tier=TIER_4_PREMIUM, txn=5_000_000,
                                   config=make_config(withdrawal=500_000, transfer=1_000_000)):
                assert cta(1, Decimal('600000'), 'withdraw')[0] is False
                assert cta(1, Decimal('400000'), 'withdraw')[0] is True
                assert cta(1, Decimal('1500000'), 'send')[0] is False

    def test_transfer_uses_max_transfer_amount(self, app):
        with app.app_context():
            with kyc_limit_patches(tier=TIER_4_PREMIUM, txn=5_000_000,
                                   config=make_config(deposit=2_000_000, transfer=1_000_000)):
                assert cta(1, Decimal('1200000'), 'send')[0] is False  # capped at 1M
                assert cta(1, Decimal('1500000'), 'deposit')[0] is True  # deposit at 2M


# ---------------------------------------------------------------------------
# DAILY CUMULATIVE (14-17)
# ---------------------------------------------------------------------------

class TestDailyCumulative:
    def test_regulatory_daily_enforced(self, app, monkeypatch):
        monkeypatch.setitem(app.config, 'WALLET_DAILY_LIMIT_LOCAL', 100_000_000)  # operational high -> regulatory wins
        mock_ledger = MagicMock()
        mock_ledger.get_daily_volume.return_value = Decimal('0')
        mock_ledger.get_monthly_volume.return_value = Decimal('0')
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       return_value=tier_info(TIER_2_STANDARD, 500000, 2_000_000, 10_000_000)), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get', return_value=None), \
                 patch('app.wallet.repositories.ledger_repository.LedgerRepository', return_value=mock_ledger):
                with pytest.raises(LimitExceededError):
                    KYCLimitService.enforce_cumulative_volume(1, 1, Decimal('2_100_000'), 'UGX', 'daily')
                # within limit
                KYCLimitService.enforce_cumulative_volume(1, 1, Decimal('50000'), 'UGX', 'daily')

    def test_ledger_daily_volume_used(self, app):
        mock_ledger = MagicMock()
        mock_ledger.get_daily_volume.return_value = Decimal('0')
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       return_value=tier_info(TIER_2_STANDARD, 500000, 2_000_000, 10_000_000)), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get',
                       side_effect=lambda cls, pk: MagicMock() if cls.__name__ == 'AccountModel' else None), \
                 patch('app.wallet.repositories.ledger_repository.LedgerRepository', return_value=mock_ledger):
                KYCLimitService.enforce_cumulative_volume(1, 1, Decimal('100'), 'UGX', 'daily')
                mock_ledger.get_daily_volume.assert_called_once()

    def test_wallet_service_enforces_operational_daily(self, app, monkeypatch):
        # WalletService._check_daily_limit enforces the OPERATIONAL Flask daily ceiling
        # (WALLET_DAILY_LIMIT_LOCAL for UGX), derived from ledger volume. Regulatory KYC
        # daily cumulative is enforced separately in WalletService._check_kyc_limits.
        ws = WalletService(db_session=MagicMock())
        ws.account_repo = MagicMock()
        ws.ledger_repo = MagicMock()
        ws.ledger_repo.get_daily_volume.return_value = Decimal('1900000')
        account = MagicMock()
        account.id = 1
        account.user_id = 1
        account.currency = 'UGX'
        ws.account_repo.get_by_id.return_value = account
        with app.app_context():
            monkeypatch.setitem(app.config, 'WALLET_DAILY_LIMIT_LOCAL', 2000000)
            with patch('app.wallet.services.wallet_service.WalletSystemConfig.get_config',
                       return_value=MagicMock(max_daily_amount=None, max_monthly_amount=None)):
                with pytest.raises(LimitExceededError):
                    ws._check_daily_limit(1, Decimal('200000'), 'UGX', 'deposit')
                ws._check_daily_limit(1, Decimal('50000'), 'UGX', 'deposit')

    def test_effective_daily_is_restrictive_min(self, app, monkeypatch):
        with app.app_context():
            monkeypatch.setitem(app.config, 'WALLET_DAILY_LIMIT_LOCAL', 10000)
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       return_value=tier_info(TIER_3_ENHANCED, 2_000_000, 7_000_000, 35_000_000)), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get', return_value=None):
                # regulatory 7M, operational 10k -> min 10k
                assert KYCLimitService.get_effective_cumulative_limit(1, 'UGX', 'daily') == Decimal('10000')
            monkeypatch.setitem(app.config, 'WALLET_DAILY_LIMIT_LOCAL', 1_000_000)
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       return_value=tier_info(TIER_1_BASIC, 100000, 400000, 2_000_000)), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get', return_value=None):
                # regulatory 400k, operational 1M -> min 400k
                assert KYCLimitService.get_effective_cumulative_limit(1, 'UGX', 'daily') == Decimal('400000')


# ---------------------------------------------------------------------------
# MONTHLY CUMULATIVE (18-21)
# ---------------------------------------------------------------------------

class TestMonthlyCumulative:
    def test_regulatory_monthly_enforced(self, app):
        mock_ledger = MagicMock()
        mock_ledger.get_daily_volume.return_value = Decimal('0')
        mock_ledger.get_monthly_volume.return_value = Decimal('9000000')
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       return_value=tier_info(TIER_2_STANDARD, 500000, 2_000_000, 10_000_000)), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get', return_value=None), \
                 patch('app.wallet.repositories.ledger_repository.LedgerRepository', return_value=mock_ledger):
                with pytest.raises(LimitExceededError):
                    KYCLimitService.enforce_cumulative_volume(1, 1, Decimal('2000000'), 'UGX', 'monthly')
                KYCLimitService.enforce_cumulative_volume(1, 1, Decimal('500000'), 'UGX', 'monthly')

    def test_ledger_monthly_volume_used(self, app):
        mock_ledger = MagicMock()
        mock_ledger.get_monthly_volume.return_value = Decimal('0')
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       return_value=tier_info(TIER_4_PREMIUM, 5_000_000, 0, 0)), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get', return_value=None), \
                 patch('app.wallet.repositories.ledger_repository.LedgerRepository', return_value=mock_ledger):
                KYCLimitService.enforce_cumulative_volume(1, 1, Decimal('100'), 'UGX', 'monthly')
                mock_ledger.get_monthly_volume.assert_called_once()

    def test_stored_account_monthly_volume_not_authoritative(self, app):
        mock_ledger = MagicMock()
        mock_ledger.get_daily_volume.return_value = Decimal('0')
        mock_ledger.get_monthly_volume.return_value = Decimal('0')
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       return_value=tier_info(TIER_2_STANDARD, 500000, 2_000_000, 10_000_000)), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get', return_value=None), \
                 patch('app.wallet.repositories.ledger_repository.LedgerRepository', return_value=mock_ledger):
                # Even if a stale stored account.monthly_volume were huge, ledger is authoritative.
                KYCLimitService.enforce_cumulative_volume(1, 1, Decimal('8000000'), 'UGX', 'monthly')  # 9M < 10M ok

    def test_max_transfer_not_monthly_ceiling(self, app):
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       return_value=tier_info(TIER_2_STANDARD, 500000, 2_000_000, 10_000_000)), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config',
                       return_value=make_config(transfer=1_000_000)), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get', return_value=None):
                monthly = KYCLimitService.get_effective_cumulative_limit(1, 'UGX', 'monthly')
                assert monthly == Decimal('10000000')
                assert monthly != Decimal('1000000')


# ---------------------------------------------------------------------------
# ROUTE INDEPENDENCE / SINGLE BOUNDARY (22)
# ---------------------------------------------------------------------------

class TestSingleBoundary:
    def test_service_and_direct_share_cumulative_boundary(self, app):
        # WalletService._check_kyc_limits enforces regulatory KYC cumulative limits via
        # KYCLimitService.check_regulatory_cumulative_limits; enforce_cumulative_volume is
        # the direct equivalent. Both must share the same ledger-derived boundary (tier-2
        # daily = 2_000_000). A 2_100_000 request exceeds; 2_000 stays under.
        mock_ledger = MagicMock()
        mock_ledger.get_daily_volume.return_value = Decimal('0')
        mock_ledger.get_monthly_volume.return_value = Decimal('0')
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       return_value=tier_info(TIER_2_STANDARD, 500000, 2_000_000, 10_000_000)), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get',
                       side_effect=lambda cls, pk: MagicMock() if cls.__name__ == 'AccountModel' else None), \
                 patch('app.wallet.repositories.ledger_repository.LedgerRepository', return_value=mock_ledger):
                # Direct helper: returns dict (not raises)
                assert KYCLimitService.check_regulatory_cumulative_limits(
                    1, 'UGX', Decimal('2000'), 2)['allowed'] is True
                # WalletService path uses the same limit
                ws = WalletService(db_session=MagicMock())
                ws.account_repo = MagicMock()
                ws._check_kyc_limits(1, Decimal('2000'), 'deposit', 'UGX', account_id=1)
                # Over the boundary: both detect the breach
                assert KYCLimitService.check_regulatory_cumulative_limits(
                    1, 'UGX', Decimal('2_100_000'), 2)['allowed'] is False
                with pytest.raises(LimitExceededError):
                    KYCLimitService.enforce_cumulative_volume(1, 1, Decimal('2_100_000'), 'UGX', 'daily')


# ---------------------------------------------------------------------------
# ORGANISATION KYB AUTHORITY (23-27)
# ---------------------------------------------------------------------------

def _org_status(is_operational, is_full, level):
    return {
        "is_operational_kyb": is_operational,
        "is_full_kyb": is_full,
        "kyb_level": level,
        "pending_requirements": [],
        "limits": {"daily": 2000000, "monthly": 10000000, "transaction": 500000},
    }


class TestOrganisationKYBAuthority:
    def test_org_L0_denied(self, app):
        with app.app_context():
            with kyc_limit_patches(org_status=_org_status(False, False, 0)):
                allowed, reason = cta(1, Decimal('1000'), 'deposit')
                assert allowed is False

    def test_org_L1_permitted_operations(self, app):
        # L1 is operational KYB (not full). Small sub-large-threshold amounts are permitted;
        # full KYB is only required for personal transfers or large-value transactions.
        with app.app_context():
            with kyc_limit_patches(org_status=_org_status(True, False, 1)):
                assert cta(1, Decimal('5000'), 'deposit')[0] is True
                assert cta(1, Decimal('5000'), 'withdraw')[0] is True
                assert cta(1, Decimal('5000'), 'send')[0] is True

    def test_org_L1_personal_transfer_requires_full_kyb(self, app):
        with app.app_context():
            with kyc_limit_patches(org_status=_org_status(True, False, 1)):
                allowed, reason = cta(
                    1, Decimal('50000'), 'send', recipient_user_id=999)
                assert allowed is False  # personal transfer forces full KYB

    def test_org_kyb_status_from_compute_status(self, app):
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier'), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get',
                       side_effect=lambda cls, pk: _org_mock(pk) if cls.__name__ == 'Organisation' else None), \
                 patch('app.identity.services.organisation_kyb_service.OrganisationKYBService.compute_status',
                       return_value=_org_status(True, True, 2)) as mock_cs:
                cta(1, Decimal('1000'), 'deposit')
                mock_cs.assert_called_once()

    def test_org_ui_and_auth_agree(self, app):
        with app.app_context():
            with kyc_limit_patches(org_status=_org_status(True, True, 2)):
                limits = KYCLimitService.get_transaction_limits(1)
                assert limits["kyc_level"] == 2
                assert cta(1, Decimal('400000'), 'deposit')[0] is True


# ---------------------------------------------------------------------------
# FAILURE SEMANTICS: fail closed, no commit (28-31)
# ---------------------------------------------------------------------------

class TestFailureSemantics:
    def test_kyc_authority_failure_fail_closed(self, app):
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       side_effect=RuntimeError("kyc down")), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get', return_value=None):
                with pytest.raises(Exception):
                    cta(1, Decimal('1000'), 'deposit')

    def test_kyb_authority_failure_org_fail_closed(self, app):
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier'), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get',
                       side_effect=lambda cls, pk: _org_mock(pk)
                       if cls.__name__ == 'Organisation' else None), \
                 patch('app.identity.services.organisation_kyb_service.OrganisationKYBService.compute_status',
                       side_effect=RuntimeError("kyb down")):
                with pytest.raises(Exception):
                    cta(1, Decimal('1000'), 'deposit')

    def test_ledger_volume_failure_fail_closed(self, app):
        mock_ledger = MagicMock()
        mock_ledger.get_daily_volume.side_effect = RuntimeError("ledger down")
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       return_value=tier_info(TIER_4_PREMIUM, 5_000_000, 1_000_000, 0)), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get', return_value=None), \
                 patch('app.wallet.repositories.ledger_repository.LedgerRepository', return_value=mock_ledger):
                with pytest.raises(Exception):
                    KYCLimitService.enforce_cumulative_volume(1, 1, Decimal('100'), 'UGX', 'daily')

    def test_authorization_helpers_do_not_commit(self, app):
        mock_ledger = MagicMock()
        mock_ledger.get_daily_volume.return_value = Decimal('0')
        with app.app_context():
            with patch('app.auth.kyc_compliance.calculate_kyc_tier',
                       return_value=tier_info(TIER_4_PREMIUM, 5_000_000, 1_000_000, 0)), \
                 patch('app.wallet.services.kyc_limit_service.WalletSystemConfig.get_config', return_value=make_config()), \
                 patch('app.wallet.services.kyc_limit_service.db.session.get', return_value=None), \
                 patch('app.wallet.repositories.ledger_repository.LedgerRepository', return_value=mock_ledger), \
                 patch('app.wallet.services.kyc_limit_service.db.session.commit') as mock_commit:
                KYCLimitService.enforce_cumulative_volume(1, 1, Decimal('100'), 'UGX', 'daily')
                mock_commit.assert_not_called()


# ---------------------------------------------------------------------------
# OWNER-CONFIG -> FRONTEND CONSISTENCY (F1-F3)
# ---------------------------------------------------------------------------

class TestOwnerConfigFrontendConsistency:
    def test_owner_config_propagates_to_effective_per_transaction(self, app):
        with app.app_context():
            with kyc_limit_patches(tier=TIER_4_PREMIUM, txn=5_000_000,
                                   config=make_config(deposit=500_000)):
                limits = KYCLimitService.get_transaction_limits(1)
                # Owner lowered deposit ceiling; effective per-transaction reflects it.
                assert limits["per_transaction"]["deposit"] == Decimal('500000')
                assert limits["per_transaction"]["deposit"] != Decimal('5000000')

    def test_display_uses_effective_daily_not_raw_regulatory(self, app, monkeypatch):
        monkeypatch.setitem(app.config, 'WALLET_DAILY_LIMIT_LOCAL', 10000)
        with app.app_context():
            with kyc_limit_patches(tier=TIER_3_ENHANCED, txn=2_000_000, daily=7_000_000,
                                   config=make_config()):
                limits = KYCLimitService.get_transaction_limits(1)
                # effective daily = min(regulatory 7M, operational 10k) = 10k
                assert limits["daily_limit"] == Decimal('10000')
                assert limits["daily_limit"] != Decimal('7000000')

    def test_no_double_cumulative_enforcement_in_api(self, app):
        # get_transaction_limits must NOT itself raise; enforcement is the service's job.
        with app.app_context():
            with kyc_limit_patches(tier=TIER_1_BASIC, txn=100000, daily=400_000,
                                   config=make_config()):
                limits = KYCLimitService.get_transaction_limits(1)
                assert "daily_limit" in limits
                assert "kyc_level" in limits
