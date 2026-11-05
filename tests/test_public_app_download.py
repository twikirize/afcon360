"""Public AFCON360 app download page contract tests."""

import pytest


def test_download_page_is_public_and_shows_both_apps(client, monkeypatch):
    """Anonymous visitors see both apps and clearly labeled GitHub preview APK links."""
    for key in (
        "AFCON360_USER_ANDROID_STORE_URL",
        "AFCON360_USER_IOS_STORE_URL",
        "AFCON360_DRIVER_ANDROID_STORE_URL",
        "AFCON360_DRIVER_IOS_STORE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    response = client.get("/download")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "AFCON360 User" in html
    assert "AFCON360 Driver" in html
    assert "Open Fan Experience" in html
    assert "Open Driver Workspace" in html
    assert 'href="/transport/driver-dashboard"' in html
    assert 'https://github.com/twikirize/afcon360/releases/download/mobile-preview/AFCON360-User-preview.apk' in html
    assert 'https://github.com/twikirize/afcon360/releases/download/mobile-preview/AFCON360-Driver-preview.apk' in html
    assert "PRE-PLAY TEST BUILDS" in html
    assert "not Google Play releases" in html
    assert html.count("COMING SOON") == 4
    assert html.count('href="/download"') == 1  # footer only
    assert html.count("Download App") == 1
    assert 'href="/" ' in html or 'href="/">Explore Pamoja on the web' in html


@pytest.mark.parametrize(
    "value",
    [
        "http://play.google.com/store/apps/details?id=space.pamoja.afcon360",
        "https://evil.example/store/apps/details?id=space.pamoja.afcon360",
        "https://user:password@play.google.com/store/apps/details?id=space.pamoja.afcon360",
        "https://play.google.com:8443/store/apps/details?id=space.pamoja.afcon360",
        "javascript:alert(1)",
    ],
)
def test_download_page_never_activates_untrusted_store_urls(client, monkeypatch, value):
    """Only HTTPS links on the expected official store hosts are rendered."""
    monkeypatch.setenv("AFCON360_USER_ANDROID_STORE_URL", value)
    response = client.get("/download")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert value not in html
    assert "COMING SOON" in html


def test_download_page_activates_valid_official_store_urls(client, monkeypatch):
    """Configured Google Play and Apple App Store URLs are rendered as links."""
    play_url = "https://play.google.com/store/apps/details?id=space.pamoja.afcon360"
    app_store_url = "https://apps.apple.com/app/id1234567890"
    monkeypatch.setenv("AFCON360_USER_ANDROID_STORE_URL", play_url)
    monkeypatch.setenv("AFCON360_USER_IOS_STORE_URL", app_store_url)

    response = client.get("/download")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f'href="{play_url}"' in html
    assert f'href="{app_store_url}"' in html
    assert 'rel="noopener noreferrer"' in html
