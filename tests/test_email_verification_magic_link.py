"""Tests for the email/phone verification magic-link + OTP design.

Covers the verification mechanics without depending on a seeded user:
* signed email token round-trips (purpose + nonce) and respects max_age.
* verify_email() rejects bad / unknown-user tokens.
* the verification email template renders a magic-link token URL and an
  accurate TTL (no hardcoded 24h).
"""
from app.auth.tokens import generate_email_token, verify_email_token
from app.auth.services import verify_email


def test_email_token_roundtrip_and_expiry():
    nonce = "abc123"
    token = generate_email_token("pub_id_1", nonce=nonce)

    data = verify_email_token(token, max_age=3600)
    assert data is not None
    assert data.get("purpose") == "verify"
    assert data.get("nonce") == nonce
    assert data.get("uid") == "pub_id_1"

    # Exceeding max_age must invalidate the token.
    assert verify_email_token(token, max_age=-1) is None


def test_verify_email_rejects_bad_and_unknown_tokens():
    assert verify_email("not-a-real-token") is False
    # Token for a user that does not exist in the DB -> False (no user found).
    token = generate_email_token("does_not_exist_user", nonce="x")
    assert verify_email(token) is False


def test_verification_email_template_renders_magic_link(app):
    from flask import render_template

    with app.test_request_context():
        html = render_template(
        "notifications/email/verification_email.html",
        data={
            "user_name": "twikirizeobed",
            "verification_code": "040425",
            "verification_link": "https://pamoja.space/verify?token=deadbeef",
            "expires_in_minutes": 30,
        },
    )
    assert "/verify?token=" in html
    assert "040425" in html
    # Accurate TTL, not the old hardcoded 24h.
    assert "30 minutes" in html
    assert "24 hours" not in html
    # Button label is a one-click verify, not "click here to verify".
    assert "Verify Email" in html
