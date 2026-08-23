"""Regression tests for the authoritative current KYC status."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.kyc.models import KycRecord
from app.kyc.services import KycService
from app.auth.kyc_compliance import _build_tier_response


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


def test_kyc_progress_contract_excludes_profile_personalization_fields():
    """KYC progress is based on compliance requirements, not profile polish."""
    response = _build_tier_response(
        achieved_tier=1,
        missing_requirements=["national_id", "selfie"],
        verification=None,
        profile=SimpleNamespace(
            nickname="Fan",
            bio="Tournament supporter",
            fan_team="Uganda",
        ),
        fulfillment_percentage=25,
    )

    assert response["fulfillment_percentage"] == 25
    assert "nickname" not in response
    assert "bio" not in response
    assert "fan_team" not in response
    assert response["missing_requirements"] == ["national_id", "selfie"]


def test_next_tier_requirements_do_not_repeat_phone_verification():
    """Phone is a prerequisite tier and must not reappear in Tier 2."""
    from app.auth.kyc_compliance import _get_next_tier_info, TIER_1_BASIC

    requirements = _get_next_tier_info(TIER_1_BASIC)

    assert requirements["next_tier_name"] == "Standard"
    assert requirements["next_tier_requirements"] == ["national_id", "selfie"]
    assert "Phone verification" not in requirements["next_tier_requirements_labels"]


def test_individual_tin_is_not_required_for_enhanced_tier():
    """TIN is a configurable requirement but is OFF by default (not an enforced individual gate)."""
    from app.auth.kyc_compliance import (
        TIER_3_ENHANCED, TIER_REQUIREMENTS, is_requirement_enabled,
    )

    # 'tin' is now part of the configurable requirement set so the Owner/Super
    # Admin can toggle it, but it defaults to OFF (individual TIN optional).
    assert "tin" in TIER_REQUIREMENTS[TIER_3_ENHANCED]["required_documents"]
    assert is_requirement_enabled("tin") is False