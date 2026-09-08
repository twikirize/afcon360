"""
Owner dashboard trust-settings integration contract.

Verifies the trust-based security subsystem end to end through the real
application wiring (routes, settings model, trust service, and template),
using repository fixtures instead of hardcoded internal user IDs.
"""

import uuid

from flask import render_template

from app.events.settings_model import EventSettings
from app.events.trust_service import EventTrustService, TrustLevel
from app.identity.models.user import User


def _new_user(db_session):
    """Create a disposable, real user row (never a hardcoded internal ID)."""
    user = User(
        email=f"trust_test_{uuid.uuid4().hex}@example.com",
        username=f"trust_test_{uuid.uuid4().hex[:8]}",
        password_hash="hashed",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_owner_trust_integration(app, db_session):
    """The owner dashboard trust settings workflow is wired end to end."""
    settings = EventSettings.get()
    assert settings is not None
    assert isinstance(settings.enable_trust_based_publishing, bool)

    user = _new_user(db_session)
    trust_level = EventTrustService.calculate_trust_level(user)
    assert trust_level in (TrustLevel.HIGH, TrustLevel.MEDIUM, TrustLevel.LOW)

    should_auto, reason = EventTrustService.should_auto_publish(user, trust_level)
    assert isinstance(should_auto, bool)
    assert isinstance(reason, str)

    rules = [str(r.rule) for r in app.url_map.iter_rules()]
    assert any("/owner/trust-settings" in rule for rule in rules)
    assert any("/trust-settings" in rule for rule in rules)

    rendered = render_template(
        "admin/trust_settings.html",
        settings=settings,
        user_analyses=[],
    )
    assert str(settings.high_trust_threshold) in rendered
    assert str(settings.medium_trust_threshold) in rendered
    for toggle in (
        "enable_trust_based_publishing",
        "enable_role_bypass",
        "enable_kyc_boost",
        "enable_account_age_boost",
        "enable_event_history_boost",
    ):
        assert f'name="{toggle}"' in rendered