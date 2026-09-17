# app/kyc/selfie_pair.py
"""
Cross-device KYC selfie pairing ("scan & selfie").

Purpose
-------
A user on a camera-less device (e.g. a desktop PC) can still complete the
identity selfie by pairing with any provisional phone. The authenticated
computer issues a short-lived, single-use pairing token and shows a QR code;
the phone scans it, captures a selfie WITHOUT logging in, and uploads the
photo back. The computer detects completion by polling and includes the
pairing nonce with its KYC submission, which consumes the stored photo as the
record's selfie.

Security model
--------------
* The pairing token is a Fernet-signed, purpose-bound payload
  (``kind=selfie_pair``) carrying the nonce + owner public id, with a short
  TTL. It is a bearer credential for one capture only.
* The pairing *state* lives in Redis (no schema change) under a namespaced
  nonce key with the same TTL. The Redis record is bound to the owner's
  user id, so a stolen token can only upload for its intended user and only a
  captured-photo result can be consumed by that same logged-in user.
* Single-use: the session status moves pending -> ready -> consumed when the
  KYC submission completes; Redis keys are deleted on consumption.
* One active pairing per user: creating a new pairing invalidates the
  previous one (prevents unbounded token accumulation / replay).
* The phone page exposes no session and no PII. It renders a minimal capture
  UI authenticated only by the signed token and can POST to a single,
  rate-limited upload endpoint (CSRF-exempt because the bearer token + TTL is
  the credential; the phone has no session to carry a CSRF token).
* Fraud deterrent: short TTL (default 300 s) + no login on the phone device;
  the capture is one-shot per token.

Graceful degradation
--------------------
When Redis is unavailable the pairing feature reports 501 (unavailable) and
users fall back to the in-browser camera or the file-picker selfie upload.
"""

import base64
import io
import json
import secrets
from datetime import datetime, timezone

from flask import current_app, jsonify, render_template, request, url_for

from app.kyc.reupload import _fernet
from app.media.service import MediaService
from app.extensions import csrf, limiter

from cryptography.fernet import InvalidToken

# Default lifetime of a pairing link (seconds). Tune via
# KYC_SELFIE_PAIR_TTL_SECONDS in the environment/config if regulators require
# a shorter window.
PAIR_TTL_SECONDS = 300

_SESSION_KEY = "kyc:selfie:pair:{nonce}"
_USER_KEY = "kyc:selfie:pair:user:{user_id}"


def _pair_ttl():
    return int(current_app.config.get("KYC_SELFIE_PAIR_TTL_SECONDS", PAIR_TTL_SECONDS))


def now_ts():
    return datetime.now(timezone.utc).isoformat()


# ── Nonce + signed token ───────────────────────────────────────────────────


def _make_nonce():
    # 12 chars of urlsafe base64 (72 bits) — compact enough for a QR payload.
    return secrets.token_urlsafe(9)[:12]


def pairing_code(nonce):
    """Short human-readable fallback code derived from the nonce."""
    return (nonce or "").replace("-", "2").replace("_", "7").upper()[-6:] or "000000"


def make_selfie_pair_token(nonce, owner_public_id):
    payload = {
        "kind": "selfie_pair",
        "nonce": str(nonce),
        "owner_public_id": str(owner_public_id),
    }
    token = _fernet().encrypt(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    return token.decode("ascii")


def load_selfie_pair_token(token, max_age=None):
    """Verify a pairing token; raises ValueError on any invalid/expired state."""
    if not token:
        raise ValueError("Missing selfie pairing token")
    try:
        payload = json.loads(
            _fernet().decrypt(
                token.encode("ascii"), ttl=max_age or _pair_ttl()
            ).decode("utf-8")
        )
    except (InvalidToken, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("This selfie link is invalid or has expired") from exc
    if not isinstance(payload, dict):
        raise ValueError("This selfie link is invalid or has expired")
    if payload.get("kind") != "selfie_pair":
        raise ValueError("This selfie link is invalid or has expired")
    if not payload.get("nonce") or not payload.get("owner_public_id"):
        raise ValueError("This selfie link is invalid or has expired")
    return payload


# ── Pairing session storage (Redis) ────────────────────────────────────────


def _redis():
    from app.extensions import redis_client
    return redis_client


def _session_key(nonce):
    return _SESSION_KEY.format(nonce=nonce)


def _user_key(user_id):
    return _USER_KEY.format(user_id=int(user_id))


def create_pair_session(user_id, owner_public_id, nonce):
    """
    Persist a new pending pairing for the owner and invalidate any previous
    active pairing of the same user. Returns True on success, False when the
    pairing store is unavailable (caller reports 501).
    """
    r = _redis()
    if not r or not hasattr(r, "get"):
        return False
    try:
        previous = r.get(_user_key(user_id))
        if previous:
            try:
                r.delete(_session_key(previous.decode("utf-8")))
            except Exception:
                pass
        r.set(_user_key(user_id), nonce, ex=_pair_ttl())
        r.setex(
            _session_key(nonce),
            _pair_ttl(),
            json.dumps({
                "user_id": int(user_id),
                "owner_public_id": str(owner_public_id),
                "status": "pending",
                "media_url": None,
                "created_ts": now_ts(),
            }),
        )
        return True
    except Exception as exc:
        current_app.logger.warning(f"KYC selfie pairing store unavailable: {exc}")
        return False


def get_pair_session(nonce):
    """Return the pairing session dict, or None when missing/expired/unreadable."""
    r = _redis()
    if not r or not nonce:
        return None
    try:
        raw = r.get(_session_key(nonce))
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (TypeError, ValueError, UnicodeError):
        return None


def _save_session(session, nonce):
    r = _redis()
    if not r:
        return False
    try:
        r.setex(_session_key(nonce), _pair_ttl(), json.dumps(session))
        return True
    except Exception as exc:
        current_app.logger.warning(f"KYC selfie pairing save failed: {exc}")
        return False


def mark_pair_ready(nonce, media_url):
    """Transition a pending pairing to ready with its stored media URL."""
    session = get_pair_session(nonce)
    if not session or session.get("status") != "pending":
        return None
    session["status"] = "ready"
    session["media_url"] = media_url
    session["ready_ts"] = now_ts()
    return _save_session(session, nonce)


def consume_pair(nonce, user_id):
    """
    Atomically consume a ready pairing on KYC submission.
    Returns (media_url, reason) where reason is ok|expired|forbidden|pending.
    """
    session = get_pair_session(nonce)
    if not session:
        return None, "expired"
    if int(session.get("user_id", -1)) != int(user_id):
        return None, "forbidden"
    if session.get("status") == "ready" and session.get("media_url"):
        r = _redis()
        if r:
            try:
                r.delete(_session_key(nonce))
                r.delete(_user_key(user_id))
            except Exception:
                pass
        return session["media_url"], "ok"
    if session.get("status") == "pending":
        return None, "pending"
    return None, "consumed"


# ── QR + media persistence ─────────────────────────────────────────────────


def qr_svg_data_uri(url):
    """Render a QR code as a base64 SVG data URI (no Pillow needed)."""
    import qrcode
    from qrcode.image.svg import SvgPathImage
    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _persist_media(file_storage, owner_public_id, owner_int_id):
    """Persist a phone-captured selfie via MediaService for the token owner."""
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None
    try:
        result = MediaService.upload_photo(
            file=file_storage,
            module="kyc",
            entity_id=owner_public_id,
            uploader_user_id=owner_int_id,
        )
        urls = result.get("urls") or {}
        url = urls.get("original") or (list(urls.values())[0] if urls else None)
        if url:
            return url
        media_id = result.get("media_id")
        if media_id:
            from app.media.models import Media
            from app.media.storage import get_storage_backend
            from app.extensions import db
            media = db.session.query(Media).filter(
                Media.public_id == media_id, Media.is_deleted == False
            ).first()
            if media and media.storage_key:
                try:
                    return get_storage_backend().get_url(media.storage_key)
                except Exception:
                    pass
        return getattr(file_storage, "filename", "")
    except Exception as exc:
        current_app.logger.warning(f"KYC companion selfie persistence failed: {exc}")
        return None


def save_selfie_data_url_for_user(data_url, owner_public_id, owner_int_id):
    """Decode a base64 JPEG/PNG data URL and persist it for the owner."""
    if not data_url or not data_url.startswith("data:image/"):
        return None
    try:
        from werkzeug.datastructures import FileStorage
        header, _, b64 = data_url.partition(",")
        content_type = (
            header[len("data:"):].split(";")[0]
            if header.startswith("data:") else "image/jpeg"
        )
        ext = "png" if "png" in content_type else "jpg"
        storage = FileStorage(
            stream=io.BytesIO(base64.b64decode(b64)),
            filename=f"selfie-companion.{ext}",
            content_type=content_type,
        )
        return _persist_media(storage, owner_public_id, owner_int_id)
    except Exception as exc:
        current_app.logger.warning(f"KYC companion selfie decode failed: {exc}")
        return None


# ── Routes (registered by routes.py -> register_selfie_pair_routes) ────────


def register_selfie_pair_routes(bp):
    """Attach the cross-device pairing routes to the KYC blueprint."""

    def _origin():
        return request.host_url.rstrip("/")

    @bp.route("/selfie/pair", methods=["POST"], endpoint="selfie_pair")
    @limiter.limit("6 per minute")
    def selfie_pair_create():
        """Authenticated desktop requests a timed, single-use phone pairing."""
        from flask_login import current_user

        if not getattr(current_user, "is_authenticated", False):
            return jsonify(error="Authentication required"), 401

        nonce = _make_nonce()
        owner_public_id = current_user.public_id
        if not create_pair_session(current_user.id, owner_public_id, nonce):
            return jsonify(
                error="Phone pairing is temporarily unavailable. "
                      "Use the on-device camera or upload a selfie photo instead.",
                code="PAIRING_UNAVAILABLE",
            ), 501

        token = make_selfie_pair_token(nonce, owner_public_id)
        companion_url = _origin() + url_for("kyc.selfie_companion", token=token)
        return jsonify(
            token=token,
            nonce=nonce,
            pairing_code=pairing_code(nonce),
            qr_svg_data_uri=qr_svg_data_uri(companion_url),
            companion_url=companion_url,
            expires_in=_pair_ttl(),
        )

    @bp.route("/selfie/companion", methods=["GET"], endpoint="selfie_companion")
    def selfie_companion_page():
        """Phone-accessible capture page. No login; authenticated by token."""
        token = request.args.get("token", "").strip()
        try:
            payload = load_selfie_pair_token(token)
            session = get_pair_session(payload["nonce"])
        except ValueError as exc:
            return render_template(
                "kyc/selfie_companion.html", error=str(exc), pairing_expired=True
            ), 410

        if not session:
            return render_template(
                "kyc/selfie_companion.html",
                error="This selfie link is invalid or has expired.",
                pairing_expired=True,
            ), 410
        if str(session.get("owner_public_id", "")) != str(payload["owner_public_id"]):
            return render_template(
                "kyc/selfie_companion.html",
                error="This selfie link is invalid or has expired.",
                pairing_expired=True,
            ), 410
        if session.get("status") == "ready":
            return render_template("kyc/selfie_companion.html", already_received=True)
        return render_template("kyc/selfie_companion.html", token=token)

    @bp.route(
        "/selfie/companion/upload",
        methods=["POST"],
        endpoint="selfie_companion_upload",
    )
    @csrf.exempt
    @limiter.limit("20 per minute")
    def selfie_companion_upload():
        """Phone uploads the captured selfie. Bearer-token authenticated."""
        auth = request.get_json(silent=True) or {}
        token = str(auth.get("token") or "").strip()
        data_url = str(auth.get("selfie_data_url") or "").strip()
        try:
            payload = load_selfie_pair_token(token)
        except ValueError as exc:
            return jsonify(error=str(exc)), 401

        session = get_pair_session(payload["nonce"])
        if not session:
            return jsonify(error="This selfie link is invalid or has expired."), 410
        if str(session.get("owner_public_id", "")) != str(payload["owner_public_id"]):
            return jsonify(error="This selfie link is invalid or has expired."), 410
        if session.get("status") != "pending":
            return jsonify(error="This selfie link has already been used."), 409

        size_limit = current_app.config.get("MAX_SELFIE_DATA_URL_BYTES", 6 * 1024 * 1024)
        if len(data_url) > size_limit:
            return jsonify(error="Captured selfie is too large to transfer."), 413

        media_url = save_selfie_data_url_for_user(
            data_url,
            session["owner_public_id"],
            int(session["user_id"]),
        )
        if not media_url:
            return jsonify(error="Could not store the selfie. Please try again."), 500

        if not mark_pair_ready(payload["nonce"], media_url):
            return jsonify(error="This selfie link is no longer usable."), 409

        return jsonify(ok=True, message="Selfie received.")

    @bp.route(
        "/selfie/companion/status", methods=["GET"], endpoint="selfie_pair_status"
    )
    @limiter.limit("60 per minute")
    def selfie_pair_status():
        """Authenticated desktop polling: pending -> ready -> consumed/expired."""
        from flask_login import current_user

        if not getattr(current_user, "is_authenticated", False):
            return jsonify(error="Authentication required"), 401

        nonce = request.args.get("nonce", "").strip()
        session = get_pair_session(nonce)
        if not session:
            return jsonify(status="expired")
        if int(session.get("user_id", -1)) != int(current_user.id):
            return jsonify(status="forbidden"), 403
        status = session.get("status")
        if status == "ready":
            return jsonify(status="ready", message="Selfie received on your phone.")
        if status == "pending":
            return jsonify(status="pending")
        return jsonify(status="consumed")