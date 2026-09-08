"""
Trust-settings template rendering contract.

Regression contract: the trust-settings template must render through Flask's
``render_template`` path (which applies context processors for
``current_user``, ``url_for``, ``csrf_token`` and ``raw_csrf_token``), never
through a bare ``app.jinja_env.get_or_select_template(...).render(...)`` call,
which bypasses those processors and raises ``UndefinedError`` on
``current_user``.
"""

from flask import render_template

from app.events.settings_model import EventSettings


def test_trust_settings_template_renders_all_dynamic_values(app, db_session):
    """The trust-settings template captures every dynamic threshold and toggle."""
    settings = EventSettings.get()

    rendered = render_template(
        "admin/trust_settings.html",
        settings=settings,
        user_analyses=[],
    )

    assert isinstance(rendered, str)
    assert len(rendered) > 0

    assert str(settings.high_trust_threshold) in rendered
    assert str(settings.medium_trust_threshold) in rendered

    for toggle in (
        "enable_trust_based_publishing",
        "enable_role_bypass",
        "enable_kyc_boost",
        "enable_account_age_boost",
        "enable_event_history_boost",
    ):
        assert f'name="{toggle}"' in rendered, f"missing toggle {toggle}"