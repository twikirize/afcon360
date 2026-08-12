"""Shared state and signed-link helpers for targeted KYC/KYB replacements."""

import base64
import hashlib
import json
from datetime import datetime, timezone

from flask import current_app
from cryptography.fernet import Fernet, InvalidToken


INDIVIDUAL_DOCUMENT_KEYS = {"document", "selfie"}
REUPLOAD_REQUEST_KEY = "__afcon360_reupload_request__"
ORGANISATION_REQUESTS_KEY = "__afcon360_kyb_reupload_requests__"


def _load_notes(notes):
    """Load structured compliance notes without losing legacy plain text."""
    if not notes:
        return {}, None
    try:
        payload = json.loads(notes)
    except (TypeError, ValueError):
        return {"_legacy_notes": str(notes)}, str(notes)
    if not isinstance(payload, dict):
        return {"_legacy_notes": str(notes)}, str(notes)
    return payload, None


def _dump_notes(payload):
    if not payload:
        return None
    if set(payload) == {"_legacy_notes"}:
        return payload["_legacy_notes"]
    return json.dumps(payload, sort_keys=True)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def set_individual_reupload_request(notes, document_key, reason, requested_by):
    """Persist a request for the primary document or selfie on a KYC record."""
    if document_key not in INDIVIDUAL_DOCUMENT_KEYS:
        raise ValueError("document_key must be 'document' or 'selfie'")
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A re-upload reason is required")

    payload, _ = _load_notes(notes)
    payload[REUPLOAD_REQUEST_KEY] = {
        "document_key": document_key,
        "reason": reason,
        "requested_by": requested_by,
        "requested_at": _now_iso(),
    }
    return _dump_notes(payload)


def get_individual_reupload_request(notes):
    """Return an individual replacement request, if one is active."""
    payload, _ = _load_notes(notes)
    request = payload.get(REUPLOAD_REQUEST_KEY)
    return request if isinstance(request, dict) else None


def clear_individual_reupload_request(notes):
    """Clear an individual request while preserving other compliance notes."""
    payload, _ = _load_notes(notes)
    payload.pop(REUPLOAD_REQUEST_KEY, None)
    return _dump_notes(payload)


def set_organisation_reupload_request(
    notes, document_id, document_type, reason, requested_by
):
    """Persist a replacement request for one organisation document."""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A re-upload reason is required")

    payload, _ = _load_notes(notes)
    requests = payload.setdefault(ORGANISATION_REQUESTS_KEY, {})
    requests[str(document_id)] = {
        "document_type": document_type,
        "reason": reason,
        "requested_by": requested_by,
        "requested_at": _now_iso(),
    }
    return _dump_notes(payload)


def get_organisation_reupload_requests(notes):
    """Return all active organisation document replacement requests."""
    payload, _ = _load_notes(notes)
    requests = payload.get(ORGANISATION_REQUESTS_KEY, {})
    return requests if isinstance(requests, dict) else {}


def clear_organisation_reupload_request(notes, document_id):
    """Clear one organisation document request and preserve other requests."""
    payload, _ = _load_notes(notes)
    requests = payload.get(ORGANISATION_REQUESTS_KEY)
    if isinstance(requests, dict):
        requests.pop(str(document_id), None)
        if not requests:
            payload.pop(ORGANISATION_REQUESTS_KEY, None)
    return _dump_notes(payload)


def get_display_notes(notes):
    """Return human-readable legacy notes without exposing the metadata envelope."""
    payload, legacy = _load_notes(notes)
    if legacy:
        return legacy
    return payload.get("_legacy_notes") if isinstance(payload, dict) else notes


def _fernet():
    """Derive an encryption key from the configured Flask secret."""
    secret = str(current_app.secret_key).encode('utf-8')
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def make_reupload_token(kind, entity_id, owner_public_id, document_key, **extra):
    """Create an opaque, signed replacement link for one authenticated user."""
    if kind not in {"individual", "organisation"}:
        raise ValueError("Unsupported re-upload target")
    payload = {
        "kind": kind,
        "entity_id": int(entity_id),
        "owner_public_id": str(owner_public_id),
        "document_key": document_key,
    }
    payload.update(extra)
    encoded = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    return _fernet().encrypt(encoded).decode('ascii')


def load_reupload_token(token, owner_public_id, max_age=60 * 60 * 24 * 30):
    """Verify a replacement token and bind it to the current user's public ID."""
    if not token:
        raise ValueError("Missing re-upload token")
    try:
        payload = json.loads(
            _fernet().decrypt(token.encode('ascii'), ttl=max_age).decode('utf-8')
        )
    except (InvalidToken, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired re-upload link") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid or expired re-upload link")
    if payload.get("owner_public_id") != str(owner_public_id):
        raise ValueError("This re-upload link belongs to another user")
    if payload.get("kind") not in {"individual", "organisation"}:
        raise ValueError("Unsupported re-upload target")
    return payload