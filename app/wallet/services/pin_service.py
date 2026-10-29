"""
app/wallet/services/pin_service.py

Delivery and verification of transaction-PIN reset codes.

The wallet transaction PIN is a second factor for moving money and is
deliberately independent of the login password. A forgotten PIN is therefore
recovered by proving control of the account's verified email address or phone
number, never by re-entering the account password.

The reset code is stored through the shared ``OTPService`` (hashed, TTL-bound,
attempt-limited) rather than a bespoke cache key, so policy stays in one place.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from flask import current_app

from app.auth.otp_service import OTPService

#: Purpose namespace for wallet PIN reset codes.
WALLET_PIN_RESET_PURPOSE = "wallet_pin_reset"

#: How long a PIN reset code stays valid, in seconds.
WALLET_PIN_RESET_OTP_TTL = 300

_VALID_METHODS = ("email", "sms")

#: Machine-readable debit-authorization outcomes. Callers inside the wallet
#: module use these to pick a redirect; callers outside the wallet module only
#: consume ``TransactionPINError.code`` and never implement PIN policy.
PIN_NOT_SET = "pin_not_set"
PIN_REQUIRED = "pin_required"
PIN_LOCKED = "pin_locked"
PIN_INVALID = "pin_invalid"

_PIN_MESSAGES = {
    PIN_NOT_SET: "Set your transaction PIN before moving money.",
    PIN_REQUIRED: "Enter your transaction PIN to confirm.",
    PIN_LOCKED: "Too many incorrect attempts. Your PIN is temporarily locked.",
    PIN_INVALID: "Incorrect transaction PIN.",
}


def authorize_debit(user, pin: str | None) -> None:
    """Authorize a user-initiated wallet debit, or raise ``TransactionPINError``.

    This is the wallet module's single debit-authorization gate. Modules that
    initiate a payment (events, accommodation, ...) pass the PIN the user
    supplied with the request and let the wallet decide; they never verify it
    themselves.

    The verification attempt is committed immediately, in its own unit of
    work. The money transaction opens and rolls back afterwards, so a failed
    attempt still counts toward the lockout instead of being discarded with
    the debit's rollback.
    """
    from app.extensions import db
    from app.wallet.exceptions import TransactionPINError

    if not user or not getattr(user, "transaction_pin_hash", None):
        raise TransactionPINError(_PIN_MESSAGES[PIN_NOT_SET], code=PIN_NOT_SET)

    pin = (pin or "").strip()
    if not pin:
        raise TransactionPINError(_PIN_MESSAGES[PIN_REQUIRED], code=PIN_REQUIRED)

    if user.verify_transaction_pin(pin, session=db.session):
        db.session.commit()
        return

    db.session.commit()
    locked_until = getattr(user, "transaction_pin_locked_until", None)
    if locked_until and locked_until > datetime.now(timezone.utc):
        raise TransactionPINError(_PIN_MESSAGES[PIN_LOCKED], code=PIN_LOCKED)
    raise TransactionPINError(_PIN_MESSAGES[PIN_INVALID], code=PIN_INVALID)


def verify_debit_pin(user, pin: str | None) -> Tuple[bool, str]:
    """Non-raising form of :func:`authorize_debit` for the wallet's own views.

    Returns ``(ok, message)``. Wallet HTML routes use this to render a flash
    message and redirect; all other modules use the raised exception instead.
    """
    from app.wallet.exceptions import TransactionPINError

    try:
        authorize_debit(user, pin)
    except TransactionPINError as exc:
        return False, exc.message
    return True, ""


def _identifier(user) -> str:
    """Cache identifier for a user's reset code (public id, never internal id)."""
    return f"user:{user.public_id}"


def send_pin_reset_otp(user, method: str) -> Dict[str, Any]:
    """Generate a reset code and deliver it to the chosen verified contact.

    Returns a dict with ``success``, ``message`` and, on failure, ``code``.
    The code is invalidated when delivery fails, so a code the user can never
    receive does not sit in the store until it expires.
    """
    method = (method or "email").strip().lower()
    if method not in _VALID_METHODS:
        return {
            "success": False,
            "code": "invalid_method",
            "message": "Choose email or SMS to receive the code.",
        }

    if method == "email":
        if not user.email or not user.email_verified:
            return {
                "success": False,
                "code": "email_unavailable",
                "message": "This account has no verified email address.",
            }
    else:
        if not user.phone or not user.phone_verified:
            return {
                "success": False,
                "code": "sms_unavailable",
                "message": "This account has no verified phone number.",
            }

    identifier = _identifier(user)
    otp = OTPService.generate_otp(length=6)

    if not OTPService.store_otp(
        identifier=identifier,
        otp=otp,
        purpose=WALLET_PIN_RESET_PURPOSE,
        ttl=WALLET_PIN_RESET_OTP_TTL,
    ):
        return {
            "success": False,
            "code": "storage_failed",
            "message": "Could not create a reset code. Please try again.",
        }

    if method == "email":
        from app.auth.email import send_pin_reset_otp_email

        delivered = send_pin_reset_otp_email(user, otp)
        result: Dict[str, Any] = {
            "success": delivered,
            "code": "sent" if delivered else "email_delivery_failed",
            "message": (
                "Reset code sent to your email address."
                if delivered
                else "We could not send the email. Try SMS or try again later."
            ),
        }
    else:
        from app.auth.phone_verification import send_sms_otp_checked

        result = send_sms_otp_checked(
            current_app.config,
            user.phone,
            otp,
            message=(
                f"Your AFCON360 wallet PIN reset code is: {otp}. "
                "It expires in 5 minutes."
            ),
        )
        result = dict(result)
        result["message"] = (
            "Reset code sent by SMS."
            if result.get("success")
            else result.get("message")
            or "SMS is unavailable. Choose email or try again later."
        )

    if not result.get("success"):
        OTPService.invalidate_otp(identifier, WALLET_PIN_RESET_PURPOSE)
        return {
            "success": False,
            "code": result.get("code") or "delivery_failed",
            "message": result.get("message") or "We could not send the code.",
        }

    return {"success": True, "method": method, "message": result.get("message")}


def reset_pin_with_otp(user, otp: str, pin: str, confirm_pin: str) -> Tuple[bool, str]:
    """Verify a reset code and replace the transaction PIN.

    The new PIN is validated before the code is checked so a malformed PIN does
    not consume one of the limited verification attempts.
    """
    otp = (otp or "").strip()
    pin = (pin or "").strip()
    confirm_pin = (confirm_pin or "").strip()

    if not otp or not pin or not confirm_pin:
        return False, "Enter the reset code and your new PIN."

    if pin != confirm_pin:
        return False, "The two PINs do not match."

    if not pin.isdigit() or len(pin) not in (4, 5, 6):
        return False, "PIN must be 4-6 digits."

    identifier = _identifier(user)
    verified, message = OTPService.verify_otp(
        identifier=identifier,
        otp=otp,
        purpose=WALLET_PIN_RESET_PURPOSE,
    )
    if not verified:
        return False, message or "Invalid or expired reset code."

    from app.extensions import db

    try:
        user.set_transaction_pin(pin, session=db.session)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return False, str(exc)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Could not reset transaction PIN for user %s", user.public_id
        )
        return False, "Could not update your PIN. Please try again."

    OTPService.invalidate_otp(identifier, WALLET_PIN_RESET_PURPOSE)
    return True, "Your transaction PIN has been reset."
