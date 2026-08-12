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
            from app.notifications.sms_service import send_sms
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
                    from app.notifications.sms_service import send_sms
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


def notify_admin_adjustment(
    user_id: int,
    amount: Decimal,
    currency: str,
    action: str,
    reason: str,
    admin_name: str
):
    """
    Notify user and administrators of a manual balance adjustment.
    
    This is a high-security notification for audit transparency.
    """
    # 1. Notify the user (Wallet Owner)
    action_verb = "credited to" if action == "deposit" else "deducted from"
    user_message = (
        f"AFCON360 Security Alert: A manual adjustment of {amount} {currency} was {action_verb} "
        f"your wallet. Reason: {reason}. If you did not expect this, contact support immediately."
    )
    _send(user_id, user_message, channel="both")

    # 2. Notify other admins (for multi-eye oversight)
    try:
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import Role
        from app.extensions import db
        
        # Find all admins, super_admins, and owners
        admin_roles = ['owner', 'super_admin', 'wallet_admin']
        admin_users = (
            db.session.query(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name.in_(admin_roles))
            .filter(User.is_deleted == False)
            .all()
        )
        
        admin_alert = (
            f"AFCON360 AUDIT: Admin {admin_name} performed a manual {action} of "
            f"{amount} {currency} on User ID {user_id}. Reason: {reason}."
        )
        
        for admin in admin_users:
            # Don't notify the admin who performed the action (they already know)
            # but usually it's good for audit if everyone gets it. 
            # We'll skip the actor if we had their ID here, but for now we notify all.
            _send(admin.id, admin_alert, channel="email") # Use email for admins to avoid SMS costs
            
    except Exception as e:
        logger.warning(f"Failed to notify other admins of adjustment: {e}")


def notify_adjustment_requested(
    request_id: str,
    requested_by: str,
    amount: Decimal,
    currency: str,
    adjustment_type: str
):
    """Notify Super Admins/Owners that a new adjustment request needs review."""
    try:
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import Role
        from app.extensions import db
        
        # Target only higher level admins
        admin_roles = ['owner', 'super_admin']
        admin_users = (
            db.session.query(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name.in_(admin_roles))
            .filter(User.is_deleted == False)
            .all()
        )
        
        alert_msg = (
            f"AFCON360 APPROVAL REQUIRED: Admin {requested_by} requested a manual {adjustment_type} "
            f"of {amount} {currency}. Request ID: {request_id}. Please review in Admin Dashboard."
        )
        
        for admin in admin_users:
            _send(admin.id, alert_msg, channel="email")
            
    except Exception as e:
        logger.warning(f"Failed to send adjustment request notification: {e}")


def notify_adjustment_approved(
    request_id: str,
    approved_by: str,
    user_id: int,
    amount: Decimal,
    currency: str,
    adjustment_type: str
):
    """Notify involved parties that an adjustment was approved."""
    try:
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import Role
        from app.extensions import db
        
        # 1. Notify the owner (this is also done by notify_admin_adjustment, 
        # but we can add more specific info here if needed)
        # For now, we rely on notify_admin_adjustment for the owner to avoid double notifications
        
        # 2. Notify Super Admins / Owners
        admin_roles = ['owner', 'super_admin']
        admin_users = (
            db.session.query(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name.in_(admin_roles))
            .filter(User.is_deleted == False)
            .all()
        )
        
        alert_msg = (
            f"AFCON360 AUDIT: Adjustment Request {request_id} ({amount} {currency} {adjustment_type}) "
            f"was APPROVED by {approved_by} and executed."
        )
        
        for admin in admin_users:
            _send(admin.id, alert_msg, channel="email")
            
    except Exception as e:
        logger.warning(f"Failed to send adjustment approval notification: {e}")


def notify_reconciliation_alert(mismatches: list):
    """Notify admins about reconciliation mismatches."""
    try:
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import Role
        from app.extensions import db
        
        admin_roles = ['owner', 'super_admin', 'wallet_admin']
        admin_users = (
            db.session.query(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name.in_(admin_roles))
            .filter(User.is_deleted == False)
            .all()
        )
        
        alert_msg = (
            f"AFCON360 CRITICAL: Wallet reconciliation found {len(mismatches)} balance mismatches! "
            f"Please check reconciliation logs immediately."
        )
        
        for admin in admin_users:
            _send(admin.id, alert_msg, channel="email")
            
    except Exception as e:
        logger.warning(f"Failed to send reconciliation alert: {e}")