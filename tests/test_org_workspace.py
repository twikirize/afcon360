from pathlib import Path


def test_organisation_workspace_has_event_accommodation_and_booking_views():
    root = Path(__file__).resolve().parents[1]
    templates = root / "templates" / "org"

    assert (templates / "events.html").exists()
    assert (templates / "accommodation.html").exists()
    assert (templates / "bookings.html").exists()


def test_organisation_dashboard_links_use_public_identifier():
    root = Path(__file__).resolve().parents[1]
    dashboard = (root / "templates" / "org" / "dashboard.html").read_text(encoding="utf-8")

    assert "org_id=org.org_id" in dashboard
    assert "org_id=org.id" not in dashboard


def test_organisation_workspace_shows_role_authority_and_operations_boundaries():
    root = Path(__file__).resolve().parents[1]
    dashboard = (root / "templates" / "org" / "dashboard.html").read_text(encoding="utf-8")

    assert "organisation_role_label" in dashboard
    assert "Operations" in dashboard
    assert "Bookings" in dashboard
    assert "org.bookings" in dashboard


def test_base_navigation_uses_canonical_context_and_post_switch():
    root = Path(__file__).resolve().parents[1]
    base = (root / "templates" / "base.html").read_text(encoding="utf-8")

    assert "nav_org_id" in base
    assert 'method="POST" action="{{ url_for(\'auth.switch_context\') }}"' in base
    assert "context='individual'" not in base