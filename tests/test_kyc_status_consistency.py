"""Regression tests for the authoritative current KYC status."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.kyc.models import KycRecord
from app.kyc.services import KycService


def test_latest_rejected_submission_overrides_an_older_approval():
    """A revoked/rejected latest submission must not remain verified."""
    now = datetime.now(timezone.utc)
    approved = SimpleNamespace(
        status="approved",
        created_at=now - timedelta(minutes=2),
    )
    rejected = SimpleNamespace(
        status="rejected",
        created_at=now,
    )
    query = MagicMock()
    query.filter_by.return_value.all.return_value = [approved, rejected]

    with patch.object(KycRecord, "query", query):
        result = KycService.get_user_verification_status(1)

    assert result["latest_record"] is rejected
    assert result["is_verified"] is False
    assert result["status"] == "rejected"