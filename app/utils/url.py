"""
Centralized absolute-URL helpers for AFCON360.

Many features (emails, QR booking passes, push notifications, webhooks) need a
fully-qualified URL that works *outside* the current HTTP request — e.g. a guest
scans a QR code on their phone, or an email is opened hours later on another
device. `request.url_root` only reflects whatever host the request happened to
hit (often an internal IP or `127.0.0.1` in dev), which produces unusable links
in production.

These helpers resolve the canonical public base URL from configuration first
(`Config.PUBLIC_BASE_URL`, sourced from the `PUBLIC_BASE_URL` env var), and
fall back to the current request host only when nothing is configured. This is
the single, standard way every module should build outward-facing URLs.
"""

from flask import current_app, has_request_context, request


def get_public_base_url() -> str:
    """
    Return the canonical public base URL (no trailing slash).

    Resolution order:
        1. ``Config.PUBLIC_BASE_URL`` (env ``PUBLICFG`` → ``PUBLIC_BASE_URL``)
        2. The current request's host URL (best-effort, dev only)
        3. Empty string (caller must handle)
    """
    base = ""
    try:
        base = (current_app.config.get("PUBLIC_BASE_URL") or "").strip()
    except Exception:
        base = ""

    if base:
        return base.rstrip("/")

    if has_request_context():
        try:
            return request.url_root.rstrip("/")
        except Exception:
            return ""

    return ""


def build_public_url(path: str) -> str:
    """Join the public base URL with a path (ensuring exactly one slash)."""
    base = get_public_base_url()
    if not path:
        return base
    return f"{base}/{path.lstrip('/')}" if base else path.lstrip("/")


def absolute_url_for(endpoint: str, **values) -> str:
    """
    Build an absolute, publicly-reachable URL for a Flask endpoint.

    The path is resolved by Flask (so route args are filled correctly), then
    prefixed with the canonical public base URL. This avoids depending on
    ``SERVER_NAME`` being configured, which is the common production case
    behind a reverse proxy.
    """
    from flask import url_for

    path = url_for(endpoint, _external=False, **values)
    return build_public_url(path)


def _external_kwargs() -> dict:
    # Retained for backward-compatibility / callers that still want to pass
    # explicit external hints to url_for. Returns {} by default now that
    # absolute_url_for builds the host itself via build_public_url.
    return {}
