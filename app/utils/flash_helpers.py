# app/utils/flash_helpers.py
"""
Helpers for ephemeral, inline UI feedback (form validation, one-shot errors).

These are NOT system notifications. They live only for the lifetime of the
current request/redirect and are rendered via get_flashed_messages(). They must
never be routed into the AFCON360 Notification System (the bell-icon inbox);
that pipeline (NotificationService / emit_event) is reserved for async state
changes (KYC submitted/approved, payment successful, booking confirmed, etc.).

Boundary rule (see AGENTS.md / notifications README):
  - Category 1 Request Validation (ephemeral)  -> flash() / template context
  - Category 2 Event-Driven Notifications        -> NotificationService / emit_event
"""

from flask import flash, get_flashed_messages

VALID_FLASH_CATEGORIES = ("success", "info", "warning", "danger")


def _normalize_category(category):
    if category in VALID_FLASH_CATEGORIES:
        return category
    if category in ("error", "danger"):
        return "danger"
    return "info"


def flash_form_error(message, category="danger"):
    """Flash an inline validation / form error. Always uses a render-safe category."""
    flash(message, _normalize_category(category))


def flash_form_errors(form, category="danger"):
    """Flash every WTForms field error as an inline validation message."""
    cat = _normalize_category(category)
    flashed = 0
    for field in getattr(form, "_fields", {}).values():
        for message in field.errors:
            flash(message, cat)
            flashed += 1
    return flashed


def flash_notice(message, category="info"):
    """Flash a neutral one-shot notice (success/info/warning)."""
    flash(message, _normalize_category(category))


def collect_flash_messages():
    """Return the current flashed messages without forcing a specific render path."""
    return get_flashed_messages(with_categories=True)
