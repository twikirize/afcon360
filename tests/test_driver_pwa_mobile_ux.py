"""Mobile-first and installable driver workspace presentation contracts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_driver_app_keeps_installable_pwa_identity():
    manifest = _read("static/transport/manifest.json")
    shell = _read("templates/transport/driver/base.html")
    worker = _read("static/transport/sw.js")

    assert '"name": "AFCON360 Driver"' in manifest
    assert '"start_url": "/transport/driver-dashboard"' in manifest
    assert '"scope": "/transport/"' in manifest
    assert '"display": "standalone"' in manifest
    assert 'rel="manifest"' in shell
    assert 'viewport-fit=cover' in shell
    assert "Never cache authenticated HTML" in worker
    assert "Never cache API responses or CSRF tokens" in worker
    assert "const VERSION = '2.0.7'" in worker


def test_mobile_dock_prioritises_five_destinations_without_removing_workspaces():
    shell = _read("templates/transport/driver/base.html")
    css = _read("static/css/modules/transport/driver-dashboard.css")

    assert 'aria-label="Driver workspace sections"' in shell
    assert 'aria-label="Primary driver navigation"' in shell
    for destination in ("home", "status", "trips", "earnings",
                        "assignments", "vehicles", "account"):
        assert f'data-ck-nav="{destination}"' in shell
    assert '.ck-dock > [data-ck-nav="status"]' in css
    assert '.ck-dock > [data-ck-nav="assignments"]' in css
    assert ".ck-dock .ck-tab" in css
    assert "min-height: 48px !important" in css


def test_driver_mobile_layout_observes_safe_area_and_small_screen_widths():
    shell = _read("templates/transport/driver/base.html")
    css = _read("static/css/modules/transport/driver-dashboard.css")

    assert 'viewport-fit=cover' in shell
    assert "env(safe-area-inset-top" in css
    assert "env(safe-area-inset-bottom" in css
    assert "@media (max-width: 430px)" in css
    assert "@media (max-width: 767px)" in css
    assert "overflow-wrap: anywhere" in css


def test_driver_controls_have_accessible_names_and_keyboard_focus():
    dashboard = _read("templates/transport/driver/driver_dashboard.html")
    shell = _read("templates/transport/driver/base.html")
    css = _read("static/css/modules/transport/driver-dashboard.css")

    assert '<h1 class="ck-hero-name">' in dashboard
    assert dashboard.count('aria-label="Set driver availability to online or offline"') == 2
    assert 'aria-label="Search transport"' in shell
    assert 'aria-label="Refresh driver workspace"' in shell
    assert 'aria-label="Return to AFCON360 home"' in shell
    assert dashboard.count("aria-label=") >= 8
    assert ":focus-visible + .toggle-slider" in css


def test_driver_workspace_sections_are_named_for_assistive_technology():
    dashboard = _read("templates/transport/driver/driver_dashboard.html")
    for name in (
        "Home workspace",
        "Driver status and preferences",
        "Trips and booking history",
        "Earnings and performance",
        "Assignments and scheduled work",
        "Vehicles",
        "Driver account settings",
    ):
        assert f'aria-label="{name}"' in dashboard


def test_driver_theme_and_motion_preferences_remain_supported():
    css = _read("static/css/modules/transport/driver-dashboard.css")
    assert "--font-family-heading: var(--font-display" in css
    assert "--font-family-body: var(--font-body" in css
    assert "--bg-body: #f2f4f2" not in css
    assert "body.dark-mode #driverDashboard" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "animation: none !important" in css
