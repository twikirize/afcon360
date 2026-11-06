"""Authenticated encryption helpers for JSON-backed integration credentials.

The database stores only a versioned Fernet envelope. The ENCRYPTION_KEY is a
root infrastructure secret and must be shared by every web/worker process that
reads these rows. Legacy plaintext dictionaries are returned only so the
service layer can re-encrypt them on the next successful read/write.
"""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

_ENVELOPE_KEY = "__afcon360_encrypted_json_v1__"


def is_encrypted_json(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get(_ENVELOPE_KEY) == 1
        and isinstance(value.get("payload"), str)
    )


def encrypt_json(value: Any) -> dict:
    if not isinstance(value, (dict, list)):
        raise TypeError("Only JSON objects and arrays can be encrypted")
    from app.utils.security import _get_fernet
    from app.utils.log_redaction import register_secret_mapping

    register_secret_mapping(value)
    serialized = json.dumps(
        value, separators=(",", ":"), ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    # No plaintext fallback: encryption/key failures must stop the write.
    token = _get_fernet().encrypt(serialized).decode("ascii")
    return {_ENVELOPE_KEY: 1, "payload": token}


def decrypt_json(value: Any) -> Any:
    if value is None:
        return {}
    if not is_encrypted_json(value):
        if isinstance(value, (dict, list)):
            return deepcopy(value)  # legacy plaintext; caller must migrate it
        raise ValueError("Stored encrypted configuration has an invalid format")

    from app.utils.security import _get_fernet
    from app.utils.log_redaction import register_secret_mapping

    try:
        decoded = _get_fernet().decrypt(value["payload"].encode("ascii"))
        result = json.loads(decoded.decode("utf-8"))
    except Exception:
        # Never return the ciphertext as though it were usable credentials.
        raise RuntimeError("Stored integration credentials could not be decrypted") from None

    if not isinstance(result, (dict, list)):
        raise ValueError("Decrypted integration configuration has an invalid format")
    register_secret_mapping(result)
    return result
