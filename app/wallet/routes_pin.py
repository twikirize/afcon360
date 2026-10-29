"""
app/wallet/routes_pin.py

Transaction PIN endpoints.
Register this blueprint in app/__init__.py alongside the main wallet blueprint.

Routes:
    POST /wallet/pin/set        - Set or change the user's transaction PIN
    POST /wallet/pin/verify     - Verify PIN (used by frontend modal before transfer)
    POST /wallet/pin/reset      - Reset PIN via OTP (when user forgets)
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.extensions import db, limiter
from app.wallet.exceptions import TransactionPINError

pin_bp = Blueprint("wallet_pin", __name__, url_prefix="/wallet/pin")


@pin_bp.route("/set", methods=["POST"])
@limiter.limit("10/minute")
@login_required
def set_pin():
    """
    Set or change the transaction PIN.

    Body: { "pin": "1234", "confirm_pin": "1234" }

    For a PIN change, also accepts:
        { "pin": "1234", "confirm_pin": "1234", "current_pin": "0000" }
    If user already has a PIN, current_pin is required.
    """
    data = request.get_json(silent=True) or {}
    pin = data.get("pin", "")
    confirm_pin = data.get("confirm_pin", "")
    current_pin = data.get("current_pin")  # only required if PIN already set

    # Basic validation
    if not pin or not confirm_pin:
        return jsonify({"success": False, "message": "pin and confirm_pin are required"}), 400

    if pin != confirm_pin:
        return jsonify({"success": False, "message": "PINs do not match"}), 400

    if not pin.isdigit() or len(pin) not in (4, 5, 6):
        return jsonify({"success": False, "message": "PIN must be 4-6 digits"}), 400

    # Load the real user object (current_user is a proxy)
    from app.identity.models.user import User
    user = User.get_by_private_id(current_user.id)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    # If user already has a PIN, require the current PIN to change it
    if user.transaction_pin_hash:
        if not current_pin:
            return jsonify({
                "success": False,
                "message": "current_pin is required to change an existing PIN",
                "requires_current_pin": True
            }), 400

        # Verify the current PIN using the model method
        ok = user.verify_transaction_pin(current_pin, session=db.session)
        if not ok:
            return jsonify({
                "success": False,
                "message": "Current PIN is incorrect or account is locked"
            }), 403

    # Set the new PIN
    try:
        user.set_transaction_pin(pin, session=db.session)
        db.session.commit()
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"PIN set error for user {user.id}: {e}")
        return jsonify({"success": False, "message": "Failed to set PIN"}), 500

    return jsonify({"success": True, "message": "Transaction PIN set successfully"})


@pin_bp.route("/verify", methods=["POST"])
@limiter.limit("10/minute")
@login_required
def verify_pin():
    """
    Verify the user's transaction PIN.
    Used by the frontend modal BEFORE submitting a transfer.

    Body: { "pin": "1234" }
    Returns: { "valid": true/false, "locked": false, "message": "..." }

    The frontend should:
    1. Call this endpoint when user submits PIN in modal
    2. Only proceed with the transfer POST if valid=true
    3. Show remaining attempts / lockout time if valid=false
    """
    data = request.get_json(silent=True) or {}
    pin = data.get("pin", "")

    if not pin:
        return jsonify({"valid": False, "message": "PIN is required"}), 400

    from app.identity.models.user import User
    user = User.get_by_private_id(current_user.id)
    if not user:
        return jsonify({"valid": False, "message": "User not found"}), 404

    # If no PIN set, tell the frontend to redirect to PIN setup
    if not user.transaction_pin_hash:
        return jsonify({
            "valid": False,
            "no_pin_set": True,
            "message": "No transaction PIN set. Please set a PIN first."
        }), 200

    # Check if locked before calling verify (to give a cleaner message)
    from datetime import datetime, timezone
    if user.transaction_pin_locked_until and datetime.now(timezone.utc) < user.transaction_pin_locked_until:
        seconds_remaining = int(
            (user.transaction_pin_locked_until - datetime.now(timezone.utc)).total_seconds()
        )
        return jsonify({
            "valid": False,
            "locked": True,
            "seconds_remaining": seconds_remaining,
            "message": f"PIN locked. Try again in {seconds_remaining // 60 + 1} minutes."
        }), 200

    ok = user.verify_transaction_pin(pin, session=db.session)
    db.session.commit()  # persist failed attempt counter

    if ok:
        return jsonify({"valid": True, "message": "PIN verified"})

    # Calculate remaining attempts for UX feedback
    max_attempts = current_app.config.get("TRANSACTION_PIN_MAX_ATTEMPTS", 5)
    attempts_used = user.transaction_pin_failed_attempts or 0
    remaining = max(0, max_attempts - attempts_used)

    return jsonify({
        "valid": False,
        "locked": user.transaction_pin_locked_until is not None,
        "attempts_remaining": remaining,
        "message": f"Incorrect PIN. {remaining} attempts remaining." if remaining > 0
                   else "PIN locked due to too many failed attempts."
    })


@pin_bp.route("/reset", methods=["POST"])
@limiter.limit("5/hour")
@login_required
def reset_pin():
    """
    Send a PIN reset code to the user's verified email or phone.

    Body: { "method": "sms" | "email" }
    """
    from app.identity.models.user import User
    from app.wallet.services.pin_service import send_pin_reset_otp

    data = request.get_json(silent=True) or {}
    user = User.get_by_private_id(current_user.id)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    result = send_pin_reset_otp(user, data.get("method", "email"))
    return jsonify(result), (200 if result.get("success") else 400)


@pin_bp.route("/reset/confirm", methods=["POST"])
@limiter.limit("10/15minutes")
@login_required
def reset_pin_confirm():
    """
    Confirm PIN reset using the delivered code + a new PIN.

    Body: { "otp": "123456", "pin": "1234", "confirm_pin": "1234" }
    """
    from app.identity.models.user import User
    from app.wallet.services.pin_service import reset_pin_with_otp

    data = request.get_json(silent=True) or {}
    user = User.get_by_private_id(current_user.id)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    ok, message = reset_pin_with_otp(
        user,
        data.get("otp", ""),
        data.get("pin", ""),
        data.get("confirm_pin", ""),
    )
    if not ok:
        return jsonify({"success": False, "message": message}), 400

    return jsonify({"success": True, "message": message})
