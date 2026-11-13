"""Regression contract for the user-facing KYC upgrade page."""

from pathlib import Path


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "kyc"
    / "upgrade.html"
)


def test_kyc_upgrade_page_does_not_expose_daily_transaction_limits():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "upgrade-card__limits" not in source
    assert "Daily limit" not in source
    assert "upgrade.limits" not in source
    assert "UGX" not in source


def test_kyc_upgrade_page_keeps_core_upgrade_information():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "upgrade.name" in source
    assert "upgrade.tier" in source
    assert "upgrade.description" in source
    assert "upgrade.required_documents" in source
    assert "upgrade.can_upgrade" in source
    assert "auth_kyc.submit_upgrade" in source
