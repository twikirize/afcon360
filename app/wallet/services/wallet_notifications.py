"""
app/wallet/services/wallet_notifications.py

Thin notification layer for wallet events.
Calls the existing SMS and email services - does NOT implement them.

RULE: Every call is wrapped in try/except.
A broken SMS provider must NEVER roll back a successful deposit.

Usage (in wallet_service.py, after each operation commits):
    from app.wallet.services.wallet_notifications import notify_deposit
    notify_deposit(user_id, amount, currency, new_balance)
"""

import logging
from decimal import Decimal
from typing import Optional

from flask import current_app

logger = logging.getLogger(__name__)


def _get_user(user_id: int):
    """Load user safely - returns None on any failure."""
    try:
        from app.identity.models.user import User
        return User.get_by_private_id(user_id)
    except Exception as e:
        logger.warning(f"Could not load user {user_id} for notification: {e}")
        return None


def _send(user_id: int, message: str, channel: str = "sms"):
    """
    Send a notification via SMS or email.
    Fails silently - never raises.
    """
    if not current_app.config.get("WALLET_NOTIFICATIONS_ENABLED", True):
        return

    try:
        user = _get_user(user_id)
        if not user:
            return

        if channel == "sms" and user.phone and user.phone_verified:
            from app.services.sms_service import send_sms
            send_sms(user.phone, message)

        elif channel == "email" and user.email and user.email_verified:
            from app.transport.services.notification_service import NotificationService
            NotificationService.send_email(
                to=user.email,
                subject="AFCON360 Wallet Update",
                body=message
            )

        # Try both if we have both verified contacts
        elif channel == "both":
            if user.phone and user.phone_verified:
                try:
                    from app.services.sms_service import send_sms
                    send_sms(user.phone, message)
                except Exception as e:
                    logger.warning(f"SMS failed for user {user_id}: {e}")
            if user.email and user.email_verified:
                try:
                    from app.transport.services.notification_service import NotificationService
                    NotificationService.send_email(
                        to=user.email,
                        subject="AFCON360 Wallet Update",
                        body=message
                    )
                except Exception as e:
                    logger.warning(f"Email failed for user {user_id}: {e}")

    except Exception as e:
        # Swallow everything - notifications are best-effort
        logger.warning(f"Notification failed for user {user_id}: {e}")


# ---------------------------------------------------------------------------
# Public notification functions - one per wallet event
# ---------------------------------------------------------------------------

def notify_deposit(user_id: int, amount: Decimal, currency: str, new_balance: Decimal):
    """Notify user their wallet was credited."""
    message = (
        f"AFCON360: Your wallet has been credited {amount} {currency}. "
        f"New balance: {new_balance} {currency}."
    )
    _send(user_id, message, channel="both")


def notify_transfer_sent(
    sender_id: int,
    amount: Decimal,
    currency: str,
    recipient_name: str,
    new_balance: Decimal,
    reference: Optional[str] = None
):
    """Notify sender that their transfer was sent."""
    ref_part = f" Ref: {reference}." if reference else ""
    message = (
        f"AFCON360: You sent {amount} {currency} to {recipient_name}.{ref_part} "
        f"New balance: {new_balance} {currency}."
    )
    _send(sender_id, message, channel="both")


def notify_transfer_received(
    recipient_id: int,
    amount: Decimal,
    currency: str,
    sender_name: str,
    new_balance: Decimal
):
    """Notify recipient that funds arrived."""
    message = (
        f"AFCON360: You received {amount} {currency} from {sender_name}. "
        f"New balance: {new_balance} {currency}."
    )
    _send(recipient_id, message, channel="both")


def notify_withdrawal_initiated(
    user_id: int,
    amount: Decimal,
    currency: str,
    reference: str,
    destination: Optional[str] = None
):
    """Notify user their withdrawal was initiated."""
    dest_part = f" to {destination}" if destination else ""
    message = (
        f"AFCON360: Withdrawal of {amount} {currency}{dest_part} initiated. "
        f"Reference: {reference}. You will be notified when complete."
    )
    _send(user_id, message, channel="both")


def notify_withdrawal_completed(
    user_id: int,
    amount: Decimal,
    currency: str,
    reference: str
):
    """Notify user their withdrawal completed."""
    message = (
        f"AFCON360: Your withdrawal of {amount} {currency} is complete. "
        f"Reference: {reference}."
    )
    _send(user_id, message, channel="both")


def notify_withdrawal_failed(
    user_id: int,
    amount: Decimal,
    currency: str,
    reason: str
):
    """Notify user their withdrawal failed."""
    message = (
        f"AFCON360: Your withdrawal of {amount} {currency} could not be completed. "
        f"Reason: {reason}. Please contact support if funds were deducted."
    )
    _send(user_id, message, channel="both")


def notify_pin_locked(user_id: int, minutes: int):
    """Notify user their PIN is locked."""
    message = (
        f"AFCON360: Your transaction PIN has been locked for {minutes} minutes "
        f"due to too many failed attempts. Contact support if this wasn't you."
    )
    _send(user_id, message, channel="both")


def notify_kyc_status_change(user_id: int, new_status: str, tier: int):
    """Notify user their KYC status changed."""
    messages = {
        "approved": f"AFCON360: Your KYC verification is approved. You are now Tier {tier}. Higher limits now apply.",
        "rejected": f"AFCON360: Your KYC verification was not approved. Please resubmit with valid documents.",
        "pending": f"AFCON360: Your KYC documents are under review. We will notify you of the outcome."
    }
    message = messages.get(new_status, f"AFCON360: Your KYC status has been updated to {new_status}.")
    _send(user_id, message, channel="both")