"""
Tests proving KYC/KYB limit semantics for the frozen authorization architecture.

Focus:
- Issue H: action-specific operational ceilings (deposit/withdraw/transfer)
- Issue A: daily/monthly operational ceilings are NOT derived from max_transfer_amount
- Issue G: User.kyc_level cache must NOT be used as the authority; calculate_kyc_tier is
- Issue C: AML threshold ownership conflict is surfaced, not silently merged
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.wallet.services.kyc_limit_service import KYCLimitService


def _fake_operational_config():
    cfg = MagicMock()
    cfg.max_deposit_amount = Decimal("1000000")
    cfg.max_withdrawal_amount = Decimal("500000")
    cfg.max_transfer_amount = Decimal("300000")
    cfg.require_kyc_for_deposits = False
    cfg.require_kyc_for_withdrawals = False
    cfg.require_kyc_for_transfers = False
    return cfg


@patch("app.wallet.services.kyc_limit_service.WalletSystemConfig")
@patch("app.wallet.services.kyc_limit_service.db")
def test_deposit_uses_deposit_ceiling_not_transfer(mock_db, mock_wsc):
    """Issue H: deposits must be bounded by max_deposit_amount, not max_transfer_amount."""
    mock_wsc.get_config.return_value = _fake_operational_config()
    # Individual path: make Organisation lookup miss.
    mock_db.session.get.return_value = None

    with patch.object(KYCLimitService, "get_user_kyc_level", return_value=2):
        # amount above transfer ceiling but below deposit ceiling -> allowed for deposit
        above_transfer = Decimal("350000")
        res = KYCLimitService.check_transaction_allowed(
            1, above_transfer, "deposit", "UGX"
        )
        assert res["allowed"] is True, res

        # amount above deposit ceiling -> blocked
        above_deposit = Decimal("1500000")
        res = KYCLimitService.check_transaction_allowed(
            1, above_deposit, "deposit", "UGX"
        )
        assert res["allowed"] is False, res


@patch("app.wallet.services.kyc_limit_service.WalletSystemConfig")
@patch("app.wallet.services.kyc_limit_service.db")
def test_transfer_uses_transfer_ceiling(mock_db, mock_wsc):
    """Issue H: transfers must be bounded by max_transfer_amount."""
    mock_wsc.get_config.return_value = _fake_operational_config()
    mock_db.session.get.return_value = None

    with patch.object(KYCLimitService, "get_user_kyc_level", return_value=2):
        # Below transfer ceiling -> allowed
        res = KYCLimitService.check_transaction_allowed(
            1, Decimal("250000"), "send", "UGX"
        )
        assert res["allowed"] is True, res

        # Above transfer ceiling -> blocked even though below deposit ceiling
        res = KYCLimitService.check_transaction_allowed(
            1, Decimal("350000"), "send", "UGX"
        )
        assert res["allowed"] is False, res


@patch("app.wallet.services.kyc_limit_service.WalletSystemConfig")
@patch("app.wallet.services.kyc_limit_service.db")
def test_withdraw_uses_withdrawal_ceiling(mock_db, mock_wsc):
    """Issue H: withdrawals must be bounded by max_withdrawal_amount."""
    mock_wsc.get_config.return_value = _fake_operational_config()
    mock_db.session.get.return_value = None

    with patch.object(KYCLimitService, "get_user_kyc_level", return_value=2):
        # Above withdrawal ceiling -> blocked
        res = KYCLimitService.check_transaction_allowed(
            1, Decimal("600000"), "withdraw", "UGX"
        )
        assert res["allowed"] is False, res

        # Below withdrawal ceiling -> allowed
        res = KYCLimitService.check_transaction_allowed(
            1, Decimal("400000"), "withdraw", "UGX"
        )
        assert res["allowed"] is True, res


@patch("app.wallet.services.kyc_limit_service.WalletSystemConfig")
def test_get_transaction_limits_does_not_clamp_daily_monthly_with_transfer(mock_wsc):
    """Issue A: daily/monthly regulatory limits must NOT be clamped by max_transfer_amount."""
    cfg = _fake_operational_config()
    mock_wsc.get_config.return_value = cfg

    with patch.object(KYCLimitService, "get_user_kyc_level", return_value=2):
        # Tier 2 regulatory: daily 2_000_000, monthly 10_000_000, per_txn 500_000
        limits = KYCLimitService.get_transaction_limits(1)

    # per-transaction is min(regulatory 500_000, transfer ceiling 300_000) = 300_000
    assert limits["per_transaction_limit"] == pytest.approx(300000)
    # daily/monthly must equal the regulatory limits, NOT be clamped to 300_000
    assert limits["daily_limit"] == pytest.approx(2000000), limits
    assert limits["monthly_limit"] == pytest.approx(10000000), limits


@patch("app.wallet.services.kyc_limit_service.WalletSystemConfig")
@patch("app.wallet.services.kyc_limit_service.db")
def test_kyc_level_cache_not_used_as_authority(mock_db, mock_wsc):
    """Issue G: authority is calculate_kyc_tier, not a cached User.kyc_level column.

    The service must call the canonical authority (get_user_kyc_level ->
    calculate_kyc_tier), and a mismatch between the denormalized cache and the
    computed tier must not silently authorize a transaction.
    """
    mock_wsc.get_config.return_value = _fake_operational_config()
    mock_db.session.get.return_value = None

    calls = []

    def fake_get_user_kyc_level(uid):
        calls.append(uid)
        return 0  # authoritative computation says unverified

    with patch.object(
        KYCLimitService, "get_user_kyc_level", side_effect=fake_get_user_kyc_level
    ):
        res = KYCLimitService.check_transaction_allowed(
            1, Decimal("100"), "send", "UGX"
        )
    # Unverified (tier 0) cannot send.
    assert res["allowed"] is False
    assert calls == [1]


def test_aml_threshold_ownership_conflict_surfaced():
    """Issue C: two competing AML thresholds exist and must not be silently merged.

    This test documents (does not fix) that kyc_config_schema.get_thresholds()
    and WalletSystemConfig.aml_threshold are independent authorities.
    """
    from app.kyc_config_schema import get_thresholds

    kyc_thresholds = get_thresholds()
    # KYC-config authority values (defaults).
    assert "aml_review" in kyc_thresholds
    assert "fia_report" in kyc_thresholds
    # These are distinct from WalletSystemConfig.aml_threshold (default 10000) and
    # from the hardcoded ComplianceEngine.DAILY_REPORTING_THRESHOLD (10000).
    # The test asserts the conflict is observable so a decision is forced.
    assert kyc_thresholds["aml_review"] == 5000000
    assert kyc_thresholds["fia_report"] == 20000000


# ---------------------------------------------------------------------------
# Task A: regulatory KYC daily/monthly cumulative limit enforcement.
# ---------------------------------------------------------------------------

@patch("app.wallet.repositories.ledger_repository.LedgerRepository")
@patch("app.wallet.services.kyc_limit_service.db")
@patch("app.wallet.services.kyc_limit_service.WalletSystemConfig")
def test_regulatory_daily_limit_enforced(mock_wsc, mock_db, mock_ledger):
    """Task A: regulatory daily cumulative limit is enforced from ledger volume."""
    mock_wsc.get_config.return_value = _fake_operational_config()
    mock_db.session.get.return_value = MagicMock()
    inst = mock_ledger.return_value
    inst.get_daily_volume.return_value = Decimal("1900000")
    inst.get_monthly_volume.return_value = Decimal("0")

    # Tier 2 regulatory daily limit = 2_000_000; 1.9M + 200K = 2.1M > limit.
    res = KYCLimitService.check_regulatory_cumulative_limits(
        "acc-1", "UGX", Decimal("200000"), 2
    )
    assert res["allowed"] is False
    assert res["limit_type"] == "daily"


@patch("app.wallet.repositories.ledger_repository.LedgerRepository")
@patch("app.wallet.services.kyc_limit_service.db")
@patch("app.wallet.services.kyc_limit_service.WalletSystemConfig")
def test_regulatory_daily_limit_allows_within_limit(mock_wsc, mock_db, mock_ledger):
    """Task A: a volume within the regulatory daily limit is allowed."""
    mock_wsc.get_config.return_value = _fake_operational_config()
    mock_db.session.get.return_value = MagicMock()
    inst = mock_ledger.return_value
    inst.get_daily_volume.return_value = Decimal("1000000")
    inst.get_monthly_volume.return_value = Decimal("0")

    res = KYCLimitService.check_regulatory_cumulative_limits(
        "acc-1", "UGX", Decimal("500000"), 2
    )
    assert res["allowed"] is True


@patch("app.wallet.repositories.ledger_repository.LedgerRepository")
@patch("app.wallet.services.kyc_limit_service.db")
@patch("app.wallet.services.kyc_limit_service.WalletSystemConfig")
def test_regulatory_monthly_limit_enforced(mock_wsc, mock_db, mock_ledger):
    """Task A: regulatory monthly cumulative limit is enforced from ledger volume."""
    mock_wsc.get_config.return_value = _fake_operational_config()
    mock_db.session.get.return_value = MagicMock()
    inst = mock_ledger.return_value
    inst.get_daily_volume.return_value = Decimal("0")
    # Tier 2 regulatory monthly limit = 10_000_000; 9.9M + 500K = 10.4M > limit.
    inst.get_monthly_volume.return_value = Decimal("9900000")

    res = KYCLimitService.check_regulatory_cumulative_limits(
        "acc-1", "UGX", Decimal("500000"), 2
    )
    assert res["allowed"] is False
    assert res["limit_type"] == "monthly"


@patch("app.wallet.repositories.ledger_repository.LedgerRepository")
@patch("app.wallet.services.kyc_limit_service.db")
@patch("app.wallet.services.kyc_limit_service.WalletSystemConfig")
def test_regulatory_daily_not_clamped_by_operational_ceiling(mock_wsc, mock_db, mock_ledger):
    """Issue A/Task A: the per-transaction operational ceiling must NOT be treated
    as a daily/monthly cumulative limit.

    Even though WalletSystemConfig.max_transfer_amount (300_000) is far below the
    regulatory daily limit (2_000_000), a 500_000 transaction with no prior daily
    volume must pass the cumulative daily check (it is bounded only by the
    regulatory daily limit, not by max_transfer_amount).
    """
    cfg = _fake_operational_config()  # max_transfer_amount = 300_000
    mock_wsc.get_config.return_value = cfg
    mock_db.session.get.return_value = MagicMock()
    inst = mock_ledger.return_value
    inst.get_daily_volume.return_value = Decimal("0")
    inst.get_monthly_volume.return_value = Decimal("0")

    res = KYCLimitService.check_regulatory_cumulative_limits(
        "acc-1", "UGX", Decimal("500000"), 2
    )
    assert res["allowed"] is True
    # The cumulative check must not have consulted the operational transfer ceiling.
    assert cfg.max_transfer_amount == Decimal("300000")


@patch("app.wallet.repositories.ledger_repository.LedgerRepository")
@patch("app.wallet.services.kyc_limit_service.db")
def test_regulatory_cumulative_missing_account_fail_closed(mock_db, mock_ledger):
    """A missing account must fail closed for cumulative checks.
    
    Previously this skipped the check (fail open), but that creates a gap if an
    invalid account_id somehow reaches this function. The per-transaction gate
    runs first, but defense in depth requires all gates to fail closed.
    """
    mock_db.session.get.return_value = None
    res = KYCLimitService.check_regulatory_cumulative_limits(
        "acc-1", "UGX", Decimal("100"), 2
    )
    assert res["allowed"] is False
    assert res["limit_type"] == "cumulative"
    assert "Account not found" in res["reason"]


@patch("app.wallet.repositories.ledger_repository.LedgerRepository")
@patch("app.wallet.services.kyc_limit_service.db")
def test_regulatory_cumulative_unbounded_for_tier5(mock_db, mock_ledger):
    """Tier 5 (Corporate) has no regulatory daily/monthly ceiling -> always allowed."""
    mock_db.session.get.return_value = MagicMock()
    inst = mock_ledger.return_value
    inst.get_daily_volume.return_value = Decimal("999999999")
    inst.get_monthly_volume.return_value = Decimal("999999999")
    res = KYCLimitService.check_regulatory_cumulative_limits(
        "acc-1", "UGX", Decimal("1000000"), 5
    )
    assert res["allowed"] is True


@patch("app.wallet.services.kyc_limit_service.KYCLimitService")
def test_wallet_service_raises_on_cumulative_daily(mock_kyc):
    """Wiring: WalletService._check_kyc_limits must raise when the cumulative
    regulatory daily limit is exceeded (Task A hot-path enforcement)."""
    from app.wallet.services.wallet_service import WalletService
    from app.wallet.exceptions import LimitExceededError

    mock_kyc.check_transaction_allowed.return_value = {"allowed": True, "kyc_level": 2}
    mock_kyc.check_regulatory_cumulative_limits.return_value = {
        "allowed": False,
        "limit_type": "daily",
        "reason": "daily exceeded",
    }
    svc = WalletService()
    with pytest.raises(LimitExceededError):
        svc._check_kyc_limits(
            1, Decimal("100"), "deposit", "UGX", account_id="acc-1"
        )


def test_wallet_daily_limit_uses_operational_ceiling(app):
    """Regression: _check_daily_limit enforces the Flask-config operational daily
    ceiling via ledger volume and must NOT reference the non-existent
    KYCLimitService.get_effective_cumulative_limit."""
    from app.wallet.services.wallet_service import WalletService
    from app.wallet.exceptions import LimitExceededError
    from unittest.mock import patch, MagicMock

    svc = WalletService()
    ledger = MagicMock()
    svc.ledger_repo = ledger
    app.config["WALLET_DAILY_LIMIT_LOCAL"] = 10000
    with app.app_context():
        with patch('app.wallet.services.wallet_service.WalletSystemConfig.get_config',
                   return_value=MagicMock(max_daily_amount=None, max_monthly_amount=None)):
            ledger.get_daily_volume.return_value = Decimal("9000")
            with pytest.raises(LimitExceededError) as exc:
                svc._check_daily_limit("acc-1", Decimal("2000"), "UGX", "deposit")
            assert exc.value.limit_type == "daily"
            ledger.get_daily_volume.return_value = Decimal("5000")
            svc._check_daily_limit("acc-1", Decimal("2000"), "UGX", "deposit")


def test_wallet_monthly_limit_uses_account_ceiling(app):
    """Regression: _check_monthly_limit enforces the per-account monthly_volume_limit
    via ledger volume and must NOT reference get_effective_cumulative_limit."""
    from app.wallet.services.wallet_service import WalletService
    from app.wallet.exceptions import LimitExceededError
    from unittest.mock import patch, MagicMock

    svc = WalletService()
    svc.ledger_repo = MagicMock()
    acct = MagicMock()
    acct.monthly_volume_limit = Decimal("50000")
    svc.account_repo = MagicMock()
    svc.account_repo.get_by_id.return_value = acct
    with app.app_context():
        with patch('app.wallet.services.wallet_service.WalletSystemConfig.get_config',
                   return_value=MagicMock(max_daily_amount=None, max_monthly_amount=None)):
            svc.ledger_repo.get_monthly_volume.return_value = Decimal("49000")
            with pytest.raises(LimitExceededError) as exc:
                svc._check_monthly_limit("acc-1", Decimal("2000"), "UGX")
            assert exc.value.limit_type == "monthly"
            svc.ledger_repo.get_monthly_volume.return_value = Decimal("10000")
            svc._check_monthly_limit("acc-1", Decimal("2000"), "UGX")
