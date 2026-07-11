# app/auth/tokens.py
from itsdangerous import URLSafeTimedSerializer
from os import getenv
from time import time

# Fail-closed on secrets (no dev defaults)
SECRET_KEY = getenv("SECRET_KEY")
SECURITY_SALT = getenv("SECURITY_SALT")

if not SECRET_KEY or SECRET_KEY.strip().lower() in {"dev-secret", "default", "changeme"}:
    raise RuntimeError("SECRET_KEY must be set to a strong value")
if not SECURITY_SALT or SECURITY_SALT.strip().lower() in {"dev-salt", "default", "changeme"}:
    raise RuntimeError("SECURITY_SALT must be set to a strong value")

_ts = URLSafeTimedSerializer(SECRET_KEY, salt=SECURITY_SALT)

def generate_token(payload: dict) -> str:
    return _ts.dumps(payload)

def verify_token(token: str, max_age: int):
    try:
        return _ts.loads(token, max_age=max_age)
    except Exception:
        return None

# Purpose-bound, time-limited tokens with single-use support
def generate_email_token(user_id: str, nonce: str | None = None) -> str:
    p = {"uid": user_id, "purpose": "verify", "iat": int(time())}
    if nonce:
        p["nonce"] = nonce
    return generate_token(p)

def verify_email_token(token: str, max_age: int):
    data = verify_token(token, max_age=max_age)
    return data if data and data.get("purpose") == "verify" else None

def generate_reset_token(user_id: str) -> str:
    # Include iat to compare against user.password_reset_at
    return generate_token({"uid": user_id, "purpose": "reset", "iat": int(time())})

def verify_reset_token(token: str, max_age: int):
    data = verify_token(token, max_age=max_age)
    return data if data and data.get("purpose") == "reset" else None
