from app.auth import otp_service, pending_registration


def test_resend_rejects_expired_registration_and_removes_email_index(monkeypatch):
    email = "expired-native@example.test"
    token = "expired-token"
    key = f"pending_signup:{token}"
    index = "pending_signup_email:" + __import__("hashlib").sha256(email.encode()).hexdigest()
    deleted = []

    monkeypatch.setattr(
        pending_registration,
        "store_get",
        lambda requested: {"email": email, "hard_expires_at": 100.0} if requested == key else None,
    )
    monkeypatch.setattr(pending_registration.time, "time", lambda: 101.0)
    monkeypatch.setattr(pending_registration, "store_delete", lambda requested: deleted.append(requested) or True)
    monkeypatch.setattr(
        pending_registration,
        "_rate_limit_check",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("rate limiter must not run for expired tokens")),
    )

    result = pending_registration.resend_pending_otp(token, ip="192.0.2.10")

    assert result.success is False
    assert result.code == "expired"
    assert key in deleted
    assert index in deleted


def test_resend_does_not_extend_original_hard_expiry(monkeypatch):
    email = "active-native@example.test"
    token = "active-token"
    key = f"pending_signup:{token}"
    original_hard_deadline = 200.0
    payload = {
        "email": email,
        "hard_expires_at": original_hard_deadline,
        "expires_at": 160.0,
        "attempts": 3,
    }
    stored = {}

    monkeypatch.setattr(pending_registration, "store_get", lambda requested: payload if requested == key else None)
    monkeypatch.setattr(pending_registration.time, "time", lambda: 150.0)
    monkeypatch.setattr(pending_registration, "_otp_ttl", lambda: 600)
    monkeypatch.setattr(pending_registration, "_rate_limit_check", lambda *args, **kwargs: None)
    monkeypatch.setattr(pending_registration, "store_set", lambda requested, value, ttl: stored.update(key=requested, payload=dict(value), ttl=ttl) or True)
    monkeypatch.setattr(otp_service.OTPService, "generate_otp", staticmethod(lambda length=6: "123456"))
    monkeypatch.setattr(otp_service.OTPService, "hash_otp", staticmethod(lambda value: "hashed-otp"))
    monkeypatch.setattr(
        otp_service.OTPService,
        "send_email_otp_checked",
        staticmethod(lambda **kwargs: {"success": True}),
    )

    result = pending_registration.resend_pending_otp(token, ip="192.0.2.11")

    assert result.success is True
    assert stored["key"] == key
    assert stored["ttl"] == 50
    assert stored["payload"]["expires_at"] == original_hard_deadline
    assert stored["payload"]["hard_expires_at"] == original_hard_deadline
    assert stored["payload"]["attempts"] == 0
