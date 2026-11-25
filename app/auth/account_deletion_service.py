"""Shared, reauthenticated account-closure lifecycle for web and mobile.

Closure is deliberately a two-phase process:

1. Request: verify intent, record a compliance ``DataSubjectRequest``, disable
   sign-in, revoke credentials, hide public content, and start a recoverable
   grace period.
2. Finalize: after the grace period, anonymize direct identifiers and keep
   only records that a legal, financial, safety, dispute or audit obligation
   requires.

The identity tombstone is never physically deleted because Wallet, bookings,
KYC and audit foreign keys still reference it. ``DataSubjectRequest`` is the
existing compliance-owned record for the request, so this lifecycle does not
require a new table or migration.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import current_app, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db

logger = logging.getLogger(__name__)

ACCOUNT_CLOSURE_CONFIRMATION = "DELETE MY ACCOUNT"
ACCOUNT_CLOSURE_NOTICE_VERSION = "2026-11-15"
ACCOUNT_CLOSURE_GRACE_DAYS = 30
ACCOUNT_CLOSURE_CANCEL_SALT = "afcon360.account-closure.cancel"

REQUIRED_ACKNOWLEDGEMENTS = {
    "understand_closure": (
        "I understand my account will be disabled now and permanently closed "
        "after the grace period."
    ),
    "grace_period": (
        "I understand I can cancel during the grace period using the link "
        "sent to my email address."
    ),
    "retention": (
        "I understand KYC/AML, wallet/ledger, booking, safety, dispute and "
        "audit records may be retained for legally required periods."
    ),
    "wallet": (
        "I confirm my wallet balance is zero and I have no pending payout or "
        "other outstanding financial obligation."
    ),
    "obligations": (
        "I confirm I have no active rides, bookings, listings, organisation "
        "ownership or unresolved compliance case."
    ),
    "public_content": (
        "I understand my public listings, posts and media will be hidden now "
        "and anonymized at closure."
    ),
    "no_guarantee_erasure": (
        "I understand closure does not erase records AFCON360 must retain by "
        "law and does not cancel money I owe."
    ),
    "privacy_notice": (
        "I have read the account-closure notice and the current mobile privacy "
        "notice, including any draft or review status displayed on that page."
    ),
}

_RETENTION_SUMMARY = (
    "Direct account and general-profile identifiers are anonymized when closure "
    "is finalized. Records may be retained only where an applicable legal, "
    "financial, safety, security or dispute-resolution obligation requires it, "
    "and only for the period supported by that obligation. This flow does not "
    "promise a blanket retention period."
)

_ACTIVE_ACCOMMODATION_STATUSES = (
    "held",
    "pending_payment",
    "pending_approval",
    "pending",
    "payment_partial",
    "confirmed",
    "checked_in",
)


class AccountDeletionError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _json_dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _parse_json(value) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _normalise_acknowledgements(value) -> dict:
    if isinstance(value, dict):
        return {str(key): True for key, accepted in value.items() if accepted}
    if isinstance(value, (list, tuple, set)):
        return {str(key): True for key in value if key}
    return {}


def _missing_acknowledgements(value) -> list[str]:
    accepted = _normalise_acknowledgements(value)
    return [key for key in REQUIRED_ACKNOWLEDGEMENTS if key not in accepted]


def _fingerprint_enabled() -> bool:
    value = current_app.config.get("ACCOUNT_CLOSURE_FINGERPRINT_ENABLED", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value is True


def _fingerprint_pepper() -> str:
    # Never fall back to SECRET_KEY: this purpose requires a separate key and
    # an explicit privacy/legal approval before it can be enabled.
    return str(current_app.config.get("ACCOUNT_CLOSURE_FINGERPRINT_KEY") or "").strip()


def _fingerprint(kind: str, value) -> str | None:
    if value is None or not _fingerprint_enabled():
        return None
    text = str(value).strip()
    if not text:
        return None

    if kind == "email":
        text = text.lower()
    elif kind == "phone":
        digits = re.sub(r"\D", "", text)
        if len(digits) > 9:
            digits = digits[-9:]
        text = digits
    elif kind == "nin":
        text = re.sub(r"\s+", "", text).upper()

    pepper = _fingerprint_pepper()
    if not pepper:
        logger.error(
            "Account-closure fingerprint key is unavailable; refusing to store an unkeyed identifier hash"
        )
        return None

    return hmac.new(
        pepper.encode("utf-8"),
        f"{kind}:{text}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _closure_fingerprints(user) -> dict:
    profile = None
    try:
        from app.profile.models import get_profile_by_user

        profile = get_profile_by_user(user)
    except Exception:
        logger.warning("Could not load profile for closure fingerprints", exc_info=True)

    return {
        "email": _fingerprint("email", getattr(user, "email", None)),
        "phone": _fingerprint("phone", getattr(user, "phone", None)),
        "nin": _fingerprint("nin", getattr(profile, "id_number", None) if profile else None),
        "key_version": "v1",
    }


def _request_number(now: datetime) -> str:
    return f"DSR-DEL-{now.strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"


def _grace_days() -> int:
    try:
        return max(1, int(current_app.config.get("ACCOUNT_CLOSURE_GRACE_DAYS", ACCOUNT_CLOSURE_GRACE_DAYS)))
    except (TypeError, ValueError):
        return ACCOUNT_CLOSURE_GRACE_DAYS


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt=ACCOUNT_CLOSURE_CANCEL_SALT,
    )


def _cancellation_token(request_row, user) -> str:
    return _serializer().dumps(
        {
            "request": str(request_row.public_id),
            "user": str(user.public_id),
        }
    )


def _cancellation_url(token: str) -> str:
    try:
        return url_for("account_closure_cancel", token=token, _external=True)
    except Exception:
        return f"/delete-account/cancel/{token}"


def _send_closure_email(user, grace_until: datetime, cancel_url: str) -> bool:
    recipient = getattr(user, "email", None)
    if not recipient or "@" not in recipient:
        return False
    try:
        from types import SimpleNamespace

        from app.notifications.channel_handlers.email import EmailHandler

        body = (
            "Hello,\n\n"
            "An AFCON360 account-closure request was recorded for this account.\n\n"
            f"Your account is disabled now. It will be permanently closed after "
            f"{grace_until.date().isoformat()} unless you cancel.\n\n"
            "Cancel the closure using this link before that date:\n"
            f"{cancel_url}\n\n"
            "After the grace period, direct profile identifiers are anonymized. "
            "KYC/AML, wallet, booking, safety, dispute and audit records may be "
            "retained where the law requires it.\n\n"
            "If you did not request this, cancel immediately and contact AFCON360 support.\n"
        )
        notification = SimpleNamespace(
            id=None,
            type="system_alert",
            subject="AFCON360 account closure scheduled",
            body=body,
            context={},
            link=cancel_url,
            user_id=getattr(user, "id", None),
            email=recipient,
        )
        result = EmailHandler().deliver(
            notification,
            {"email": recipient, "user_id": getattr(user, "id", None)},
        )
        return bool(result.get("success"))
    except Exception:
        logger.exception("Account-closure email delivery failed")
        return False


def _open_compliance_case(user_id: int):
    from app.admin.compliance.models import ComplianceCase, ComplianceCaseStatus

    open_statuses = [
        ComplianceCaseStatus.OPEN,
        ComplianceCaseStatus.IN_REVIEW,
        ComplianceCaseStatus.PENDING_INFO,
        ComplianceCaseStatus.ESCALATED,
    ]
    return (
        ComplianceCase.query.filter(
            ComplianceCase.user_id == user_id,
            ComplianceCase.status.in_(open_statuses),
        )
        .order_by(ComplianceCase.id.asc())
        .first()
    )


def _wallet_snapshot(user_id: int) -> dict:
    from app.wallet.models.ledger import AccountModel
    from app.wallet.models.payout import PayoutRequest
    from app.wallet.repositories.wallet_repository import WalletRepository
    from app.accommodation.models.host_profile import HostProfile

    wallet_repo = WalletRepository()
    balances: dict[str, str] = {}
    total = Decimal("0")
    host_pending = Decimal("0")

    try:
        accounts = (
            AccountModel.query.filter(AccountModel.user_id == user_id)
            .order_by(AccountModel.currency.asc())
            .all()
        )
        for account in accounts:
            balance_data = wallet_repo.get_balance(user_id, currency=account.currency)
            amount = Decimal(str(balance_data.get("balance") or "0"))
            total += amount
            if amount != 0:
                balances[account.currency] = str(amount)

        pending_payouts = (
            PayoutRequest.query.filter(
                PayoutRequest.agent_id == user_id,
                PayoutRequest.status.in_(("pending", "approved")),
            ).count()
        )

        host = HostProfile.query.filter_by(
            user_id=user_id,
            is_deleted=False,
        ).first()
        if host is not None and host.pending_payout is not None:
            host_pending = Decimal(str(host.pending_payout or "0"))
    except Exception as exc:
        logger.exception("Could not verify all wallet and payout obligations during account closure")
        raise AccountDeletionError(
            "wallet_check_unavailable",
            "AFCON360 could not verify every wallet balance and payout obligation. Please try again.",
            503,
        ) from exc

    return {
        # Kept for audit compatibility only; do not compare balances across currencies.
        "balance": str(total),
        "balances_by_currency": balances,
        "pending_payout_requests": pending_payouts,
        "host_pending_payout": str(host_pending),
    }


def _has_outstanding_wallet_balance(snapshot: dict) -> bool:
    """Check every currency independently; unlike currencies must never net off."""
    balances = snapshot.get("balances_by_currency") or {}
    for amount in balances.values():
        try:
            if Decimal(str(amount)) != 0:
                return True
        except (InvalidOperation, TypeError, ValueError):
            # Unknown or malformed values are not evidence of a zero balance.
            return True
    return False


def _revoke_user_sessions(user, now: datetime, reason: str) -> list[str]:
    """Revoke browser and device sessions inside the caller's transaction."""
    from app.auth.sessions import ServerSession
    from app.identity.models.user import Session as DeviceSession

    device_sessions = DeviceSession.query.filter_by(
        user_id=user.id,
        revoked_at=None,
    ).all()
    for session in device_sessions:
        session.revoked_at = now
        session.revoked_reason = reason

    server_sessions = ServerSession.query.filter_by(
        user_id=str(user.public_id),
        is_revoked=False,
    ).all()
    for session in server_sessions:
        session.is_revoked = True

    return [session.session_id for session in device_sessions]


def _mark_mobile_sessions_revoked(session_ids) -> None:
    """Best-effort Redis cleanup after the database transaction commits."""
    if not session_ids:
        return
    try:
        from app.auth.mobile_tokens import mark_mobile_session_revoked

        for session_id in session_ids:
            try:
                mark_mobile_session_revoked(session_id)
            except Exception:
                logger.warning(
                    "Redis token cleanup deferred for closed-account device session",
                    exc_info=True,
                )
    except Exception:
        logger.warning(
            "Mobile Redis token cleanup is unavailable during account closure",
            exc_info=True,
        )


def _assert_no_financial_or_operator_obligations(user) -> dict:
    snapshot = _wallet_snapshot(user.id)
    try:
        host_pending = Decimal(str(snapshot["host_pending_payout"]))
        pending_payouts = int(snapshot["pending_payout_requests"])
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise AccountDeletionError(
            "wallet_check_unavailable",
            "AFCON360 could not verify every wallet and payout obligation. Please try again.",
            503,
        ) from exc

    if _has_outstanding_wallet_balance(snapshot) or host_pending != 0 or pending_payouts > 0:
        raise AccountDeletionError(
            "wallet_balance_outstanding",
            "Withdraw or resolve your wallet balance, host pending payout and any "
            "pending payout request before closing this account.",
            409,
        )

    from app.identity.models.organisation import Organisation

    owned_org = (
        Organisation.query.filter(
            Organisation.primary_contact_user_id == user.id,
            Organisation.is_deleted.is_(False),
        )
        .order_by(Organisation.id.asc())
        .first()
    )
    if owned_org is not None:
        raise AccountDeletionError(
            "organisation_ownership_pending",
            "Transfer the primary-contact role for your organisation to another "
            "member before closing this account.",
            409,
        )

    try:
        from app.identity.models.organisation_member import (
            OrganisationMember,
            OrgRole,
            OrgUserRole,
        )

        owner_membership = (
            OrgUserRole.query.join(
                OrgRole,
                OrgUserRole.role_id == OrgRole.id,
            )
            .join(
                OrganisationMember,
                OrgUserRole.organisation_member_id == OrganisationMember.id,
            )
            .filter(
                OrganisationMember.user_id == user.id,
                OrganisationMember.is_active.is_(True),
                OrganisationMember.is_deleted.is_(False),
                OrgRole.template_name == "org_owner",
            )
            .first()
        )
        if owner_membership is not None:
            raise AccountDeletionError(
                "organisation_ownership_pending",
                "Transfer organisation ownership to another member before closing "
                "this account.",
                409,
            )
    except AccountDeletionError:
        raise
    except Exception as exc:
        logger.exception("Could not check organisation ownership during account closure")
        raise AccountDeletionError(
            "organisation_ownership_check_unavailable",
            "AFCON360 could not verify organisation ownership. Please try again.",
            503,
        ) from exc

    return snapshot


def _assert_no_active_accommodation_obligations(user) -> None:
    from sqlalchemy import or_

    from app.accommodation.models.booking import AccommodationBooking

    active_statuses = list(_ACTIVE_ACCOMMODATION_STATUSES)
    guest_booking = (
        AccommodationBooking.query.filter(
            AccommodationBooking.is_deleted.is_(False),
            AccommodationBooking.status.in_(active_statuses),
            or_(
                AccommodationBooking.guest_user_id == user.id,
                AccommodationBooking.booked_by_user_id == user.id,
                AccommodationBooking.booking_owner_id == user.id,
            ),
        )
        .order_by(AccommodationBooking.id.asc())
        .first()
    )
    if guest_booking is not None:
        raise AccountDeletionError(
            "accommodation_booking_pending",
            "Complete or cancel your active accommodation booking before closing "
            "this account.",
            409,
        )

    host_booking = (
        AccommodationBooking.query.filter(
            AccommodationBooking.host_user_id == user.id,
            AccommodationBooking.is_deleted.is_(False),
            AccommodationBooking.status.in_(active_statuses),
        )
        .order_by(AccommodationBooking.id.asc())
        .first()
    )
    if host_booking is not None:
        raise AccountDeletionError(
            "host_booking_pending",
            "Resolve your active host bookings before closing this account.",
            409,
        )


def _suppress_public_content(user, now: datetime) -> dict:
    state: dict = {
        "properties": [],
        "posts": [],
        "media": [],
        "fan_profile": None,
        "host_profile": None,
        "organizer_profile": None,
        "memberships": [],
        "driver_profile": None,
    }

    try:
        from app.accommodation.models.property import Property

        properties = Property.query.filter(Property.owner_user_id == user.id).all()
        for prop in properties:
            state["properties"].append(
                {
                    "id": prop.id,
                    "status": prop.status,
                    "visibility": prop.visibility,
                    "is_publicly_visible": prop.is_publicly_visible,
                    "is_active": prop.is_active,
                    "archived_at": prop.archived_at.isoformat() if prop.archived_at else None,
                    "archived_reason": prop.archived_reason,
                }
            )
            prop.status = "archived"
            prop.visibility = "hidden"
            prop.is_publicly_visible = False
            prop.is_active = False
            prop.archived_at = now
            prop.archived_reason = "account_closure"
    except Exception as exc:
        db.session.rollback()
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.feed.models import Post

        posts = Post.query.filter(
            Post.author_id == user.id,
            Post.status != "deleted",
        ).all()
        for post in posts:
            state["posts"].append({"id": post.id, "status": post.status})
            post.status = "archived"
    except Exception as exc:
        db.session.rollback()
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.media.models import Media

        media_rows = Media.query.filter(
            Media.uploaded_by == user.id,
            Media.is_deleted.is_(False),
        ).all()
        retained_modules = {"kyc", "compliance", "individual_verification", "identity"}
        for media in media_rows:
            if (media.module or "").lower() in retained_modules:
                continue
            state["media"].append(
                {
                    "id": media.id,
                    "is_deleted": media.is_deleted,
                    "is_public": media.is_public,
                }
            )
            media.is_deleted = True
            media.deleted_at = now
            media.is_public = False
    except Exception as exc:
        db.session.rollback()
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.fan.models import FanProfile

        fan = FanProfile.query.filter_by(user_id=user.id, is_deleted=False).first()
        if fan is not None:
            state["fan_profile"] = {
                "id": fan.id,
                "is_active": fan.is_active,
                "deactivated_at": fan.deactivated_at.isoformat() if fan.deactivated_at else None,
                "favorite_teams": fan.favorite_teams,
                "favorite_sports": fan.favorite_sports,
                "tournament_notifications": fan.tournament_notifications,
                "match_reminders": fan.match_reminders,
                "team_news": fan.team_news,
                "social_features_enabled": fan.social_features_enabled,
            }
            fan.is_active = False
            fan.deactivated_at = now
            fan.favorite_teams = "[]"
            fan.favorite_sports = "[]"
            fan.tournament_notifications = False
            fan.match_reminders = False
            fan.team_news = False
            fan.social_features_enabled = False
    except Exception as exc:
        db.session.rollback()
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.accommodation.models.host_profile import HostProfile

        host = HostProfile.query.filter_by(user_id=user.id, is_deleted=False).first()
        if host is not None:
            state["host_profile"] = {
                "id": host.id,
                "is_active_host": host.is_active_host,
            }
            host.is_active_host = False
    except Exception as exc:
        db.session.rollback()
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.events.models import OrganizerProfile

        organizer = OrganizerProfile.query.filter_by(
            user_id=user.id,
            is_deleted=False,
        ).first()
        if organizer is not None:
            state["organizer_profile"] = {
                "id": organizer.id,
                "status": organizer.status,
            }
            organizer.status = "suspended"
    except Exception as exc:
        db.session.rollback()
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.identity.models.organisation_member import OrganisationMember

        memberships = OrganisationMember.query.filter(
            OrganisationMember.user_id == user.id,
            OrganisationMember.is_active.is_(True),
        ).all()
        for membership in memberships:
            state["memberships"].append(
                {"id": membership.id, "is_active": membership.is_active}
            )
            membership.is_active = False
    except Exception as exc:
        db.session.rollback()
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.transport.models import DriverProfile

        driver = DriverProfile.query.filter_by(user_id=user.id, is_deleted=False).first()
        if driver is not None:
            state["driver_profile"] = {
                "id": driver.id,
                "is_online": driver.is_online,
                "is_available": driver.is_available,
            }
            driver.is_online = False
            driver.is_available = False
    except Exception as exc:
        db.session.rollback()
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    return state


def _restore_public_content(state: dict, now: datetime) -> None:
    state = state or {}

    try:
        from app.accommodation.models.property import Property

        for saved in state.get("properties") or []:
            prop = db.session.get(Property, saved.get("id"))
            if prop is None:
                continue
            prop.status = saved.get("status")
            prop.visibility = saved.get("visibility")
            prop.is_publicly_visible = saved.get("is_publicly_visible")
            prop.is_active = saved.get("is_active")
            prop.archived_at = (
                datetime.fromisoformat(saved["archived_at"])
                if saved.get("archived_at")
                else None
            )
            prop.archived_reason = saved.get("archived_reason")
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.feed.models import Post

        for saved in state.get("posts") or []:
            post = db.session.get(Post, saved.get("id"))
            if post is not None:
                post.status = saved.get("status")
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.media.models import Media

        for saved in state.get("media") or []:
            media = db.session.get(Media, saved.get("id"))
            if media is None:
                continue
            media.is_deleted = bool(saved.get("is_deleted"))
            media.deleted_at = None if not media.is_deleted else now
            media.is_public = bool(saved.get("is_public"))
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.fan.models import FanProfile

        saved = state.get("fan_profile")
        if saved:
            fan = db.session.get(FanProfile, saved.get("id"))
            if fan is not None:
                fan.is_active = bool(saved.get("is_active"))
                fan.deactivated_at = (
                    datetime.fromisoformat(saved["deactivated_at"])
                    if saved.get("deactivated_at")
                    else None
                )
                fan.favorite_teams = saved.get("favorite_teams") or "[]"
                fan.favorite_sports = saved.get("favorite_sports") or '["football"]'
                fan.tournament_notifications = bool(saved.get("tournament_notifications"))
                fan.match_reminders = bool(saved.get("match_reminders"))
                fan.team_news = bool(saved.get("team_news"))
                fan.social_features_enabled = bool(saved.get("social_features_enabled"))
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.accommodation.models.host_profile import HostProfile

        saved = state.get("host_profile")
        if saved:
            host = db.session.get(HostProfile, saved.get("id"))
            if host is not None:
                host.is_active_host = bool(saved.get("is_active_host"))
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.events.models import OrganizerProfile

        saved = state.get("organizer_profile")
        if saved:
            organizer = db.session.get(OrganizerProfile, saved.get("id"))
            if organizer is not None:
                organizer.status = saved.get("status")
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.identity.models.organisation_member import OrganisationMember

        for saved in state.get("memberships") or []:
            membership = db.session.get(OrganisationMember, saved.get("id"))
            if membership is not None:
                membership.is_active = bool(saved.get("is_active"))
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.transport.models import DriverProfile

        saved = state.get("driver_profile")
        if saved:
            driver = db.session.get(DriverProfile, saved.get("id"))
            if driver is not None:
                driver.is_online = bool(saved.get("is_online"))
                driver.is_available = bool(saved.get("is_available"))
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc


def _anonymize_supporting_profiles(user, now: datetime) -> dict:
    summary: dict = {}

    try:
        from app.fan.models import FanProfile

        fan = FanProfile.query.filter_by(user_id=user.id).first()
        if fan is not None:
            fan.is_active = False
            fan.deactivated_at = now
            fan.favorite_teams = "[]"
            fan.favorite_sports = "[]"
            fan.tournament_notifications = False
            fan.match_reminders = False
            fan.team_news = False
            fan.social_features_enabled = False
            summary["fan_profile"] = True
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.accommodation.models.guest_profile import GuestProfile

        guest = GuestProfile.query.filter_by(guest_user_id=user.id).first()
        if guest is not None:
            guest.special_requests_template = None
            guest.dietary_restrictions = None
            guest.accessibility_needs = None
            guest.internal_notes = None
            guest.marketing_opt_in = False
            guest.sms_notifications = False
            guest.email_notifications = False
            summary["guest_profile"] = True
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.accommodation.models.guest_identity import GuestIdentityProfile

        guest_identity = GuestIdentityProfile.query.filter_by(user_id=user.id).first()
        if guest_identity is not None:
            guest_identity.passport_number = None
            guest_identity.national_id = None
            guest_identity.document_image = None
            guest_identity.notes = None
            summary["guest_identity"] = True
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.accommodation.models.host_profile import HostProfile

        host = HostProfile.query.filter_by(user_id=user.id).first()
        if host is not None:
            host.is_active_host = False
            host.onboarding_completed = False
            host.tax_id = None
            host.tax_country = None
            host.vat_number = None
            host.extra_data = {}
            summary["host_profile"] = True
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.events.models import OrganizerProfile

        organizer = OrganizerProfile.query.filter_by(user_id=user.id).first()
        if organizer is not None:
            organizer.status = "suspended"
            organizer.onboarding_completed = False
            organizer.organization_name = None
            organizer.bio = None
            organizer.revoked_at = now
            summary["organizer_profile"] = True
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.identity.models.organisation_member import OrganisationMember

        memberships = OrganisationMember.query.filter_by(user_id=user.id).all()
        for membership in memberships:
            membership.is_active = False
            membership.job_title = None
            membership.meta = {}
        summary["organisation_memberships"] = len(memberships)
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.accommodation.models.property import Property

        properties = Property.query.filter(Property.owner_user_id == user.id).all()
        for prop in properties:
            prop.status = "archived"
            prop.visibility = "hidden"
            prop.is_publicly_visible = False
            prop.is_active = False
            prop.archived_at = now
            prop.archived_reason = "account_closure"
            prop.main_image = None
            prop.gallery = []
            prop.moderation_notes = None
        summary["properties_archived"] = len(properties)
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.feed.models import Post

        posts = Post.query.filter(Post.author_id == user.id).all()
        for post in posts:
            # Archive the record for aggregate/history integrity, but remove
            # the content and author link that could identify the closed user.
            post.status = "archived"
            post.visibility = "private"
            post.body = ""
            post.media_url = None
            post.link_url = None
            post.link_title = None
            post.source_module = None
            post.source_item_id = None
            post.source_item_type = None
            post.is_pinned = False
            post.author_id = None
            post.author_type = "system"
        summary["posts_archived"] = len(posts)
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    try:
        from app.media.models import Media
        from app.media.storage import get_storage_backend

        media_rows = Media.query.filter(Media.uploaded_by == user.id).all()
        retained_modules = {"kyc", "compliance", "individual_verification", "identity"}
        deleted = 0
        for media in media_rows:
            if (media.module or "").lower() in retained_modules:
                continue
            if not media.is_deleted:
                if media.storage_key:
                    try:
                        get_storage_backend().delete(media.storage_key)
                    except Exception as exc:
                        logger.exception("Could not delete retained media object during account closure")
                        raise AccountDeletionError(
                            "media_erasure_failed",
                            "AFCON360 could not complete media erasure. The closure will be retried.",
                            503,
                        ) from exc
                media.is_deleted = True
                media.deleted_at = now
                media.is_public = False
                media.caption = None
                # Remove the durable object locator and file-derived metadata
                # after storage deletion succeeds. A soft-deleted row must not
                # retain URLs, filenames or content hashes that identify the
                # closed user's personal media.
                media.storage_key = None
                media.video_url = None
                media.original_filename = None
                media.file_size = None
                media.mime_type = None
                media.sha256_hash = None
                media.perceptual_hash = None
                media.thumbnail_url = None
                media.urls = {}
                media.upload_session_id = None
                media.processing_metadata = None
                media.error_message = None
                media.failed_at = None
                media.cleaned_at = now
                media.uploaded_by = None
                media.entity_id = "anonymized"
                media.module = "anonymized"
                deleted += 1
        summary["media_deleted"] = deleted
    except Exception as exc:
        logger.exception("Required account-closure data operation failed")
        raise AccountDeletionError(
            "account_closure_data_update_failed",
            "AFCON360 could not complete every required account-closure data update. Please retry or contact support.",
            503,
        ) from exc

    return summary


def _anonymize_identity(user, now: datetime) -> tuple[dict, list[str]]:
    from sqlalchemy import func

    from app.identity.models.user import APIKey, MFASecret

    summary: dict = {}

    mobile_session_ids = _revoke_user_sessions(user, now, "account_closure")
    summary["active_device_sessions_revoked"] = len(mobile_session_ids)

    from app.transport.models import DriverProfile

    driver_profile = DriverProfile.query.filter_by(
        user_id=user.id,
        is_deleted=False,
    ).with_for_update(of=DriverProfile).first()

    user.is_deleted = True
    user.is_active = False
    user.deleted_at = now
    user.email = f"deleted_{user.public_id}@deleted.local"
    user.username = f"deleted_{user.public_id}"
    user.email_verified = False
    user.phone_verified = False
    user.mfa_enabled = False
    user.security_question = None
    user.security_answer_hash = None
    user.recovery_code = None
    user.transaction_pin_hash = None
    user.transaction_pin_failed_attempts = 0
    user.transaction_pin_locked_until = None
    user.is_agent = False
    if hasattr(user, "phone"):
        user.phone = None
    if hasattr(user, "agent_code"):
        user.agent_code = None
    if hasattr(user, "email_verify_nonce"):
        user.email_verify_nonce = None
    if hasattr(user, "password_hash"):
        user.set_password(secrets.token_urlsafe(64))

    from app.profile.models import get_profile_by_user

    profile = get_profile_by_user(user)
    if profile is not None:
        profile.is_deleted = True
        profile.deleted_at = now
        profile.full_name = "Deleted account"
        profile.display_name = "Deleted account"
        profile.date_of_birth = None
        profile.gender = None
        profile.nationality = None
        profile.address = None
        profile.city = None
        profile.country = None
        profile.phone_number = None
        profile.email = None
        profile.email_verified = False
        profile.phone_verified = False
        profile.fan_team = None
        profile.avatar_url = None
        profile.bio = None
        profile.id_type = None
        profile.id_number = None
        profile.id_document_url = None
        profile.id_document_mime = None
        profile.id_document_size = None
        profile.rejected_reason = None
        profile.preferred_timezone = None
        summary["profile_anonymized"] = True

    if driver_profile is not None:
        driver_profile.is_deleted = True
        driver_profile.is_online = False
        driver_profile.is_available = False
        driver_profile.last_seen_at = None
        driver_profile.last_location = None
        driver_profile.location_updated_at = None
        driver_profile.emergency_contact_name = None
        driver_profile.emergency_contact_phone = None
        driver_profile.emergency_contact_relationship = None
        driver_profile.license_number_encrypted = None
        driver_profile.background_check_reference = None
        summary["driver_profile_anonymized"] = True

    for secret in MFASecret.query.filter_by(user_id=user.id, is_active=True).all():
        secret.is_active = False
        secret.secret = "revoked"
        secret.backup_codes = None
        secret.device_name = None
        secret.last_used = None

    user_api_keys = APIKey.query.filter(
        APIKey.owner_id == user.id,
        func.lower(APIKey.owner_type) == "user",
        APIKey.revoked_at.is_(None),
    ).all()
    for api_key in user_api_keys:
        api_key.revoked_at = now
    summary["api_keys_revoked"] = len(user_api_keys)

    summary.update(_anonymize_supporting_profiles(user, now))
    return summary, mobile_session_ids


def request_account_deletion(
    *,
    user,
    password,
    confirmation: str,
    mfa_code: str = "",
    ip_address: str | None = None,
    user_agent: str | None = None,
    acknowledgements=None,
    surface: str = "web",
) -> dict:
    """Reauthenticate, record a grace-period closure, and disable sign-in.

    The caller must render or return the cancellation link exactly once. The
    account remains recoverable until the grace period expires.
    """
    if confirmation != ACCOUNT_CLOSURE_CONFIRMATION:
        raise AccountDeletionError(
            "deletion_confirmation_invalid",
            f'Type "{ACCOUNT_CLOSURE_CONFIRMATION}" exactly to confirm.',
            400,
        )
    if not isinstance(password, str) or not password or len(password) > 128:
        raise AccountDeletionError(
            "password_required",
            "Enter your current password to confirm account deletion.",
            400,
        )

    if user is None or not getattr(user, "is_active", False) or getattr(user, "is_deleted", False):
        raise AccountDeletionError(
            "account_inactive",
            "This account is already inactive or cannot be deleted from this session.",
            403,
        )
    if getattr(user, "is_app_owner", lambda: False)():
        raise AccountDeletionError(
            "owner_deletion_blocked",
            "The platform owner account cannot be deleted through self-service.",
            403,
        )
    if bool(getattr(user, "is_protected", False)):
        raise AccountDeletionError(
            "protected_account",
            "This protected account must be closed through AFCON360's authorized security process.",
            403,
        )

    mfa_verified = False
    try:
        if not user.verify_password(password):
            raise AccountDeletionError(
                "password_invalid",
                "The current password could not be verified.",
                401,
            )

        from app.identity.models.user import MFASecret

        active_mfa_rows = MFASecret.query.filter_by(
            user_id=user.id,
            is_active=True,
        ).all()
        unsupported_mfa = [
            row.mfa_type for row in active_mfa_rows if row.mfa_type != "totp"
        ]
        if unsupported_mfa:
            raise AccountDeletionError(
                "mfa_method_unsupported",
                "This account uses an MFA method that cannot currently be reverified "
                "in the self-service deletion flow. Update to an authenticator app "
                "or contact AFCON360 support.",
                422,
            )
        active_mfa = next(
            (row for row in active_mfa_rows if row.mfa_type == "totp"),
            None,
        )
        if getattr(user, "mfa_enabled", False) or active_mfa_rows:
            if active_mfa is None:
                raise AccountDeletionError(
                    "mfa_enrollment_unavailable",
                    "Your account requires MFA, but no active authenticator is "
                    "available. Restore MFA through AFCON360 support before "
                    "deleting this account.",
                    403,
                )
            if not mfa_code:
                raise AccountDeletionError(
                    "mfa_required",
                    "Enter your current authenticator or backup code.",
                    401,
                )
            from app.auth.routes import _verify_mfa_token

            if not _verify_mfa_token(
                user,
                mfa_code,
                backup_code=(len(mfa_code) == 8),
            ):
                raise AccountDeletionError(
                    "mfa_invalid",
                    "The authenticator code is invalid or expired.",
                    401,
                )
            mfa_verified = True
    except AccountDeletionError:
        raise
    except Exception as exc:
        db.session.rollback()
        logger.exception("Account-closure reauthentication failed")
        raise AccountDeletionError(
            "deletion_verification_unavailable",
            "AFCON360 could not verify this deletion request.",
            503,
        ) from exc

    missing = _missing_acknowledgements(acknowledgements)
    if missing:
        raise AccountDeletionError(
            "acknowledgements_required",
            "Accept every required account-closure notice before continuing.",
            400,
        )

    from app.admin.compliance.models import (
        DataSubjectRequest,
        DataSubjectRequestStatus,
        DataSubjectRequestType,
    )
    from app.identity.models.user import User

    locked_user = User.query.filter_by(id=user.id).with_for_update(of=User).first()
    if locked_user is None or not locked_user.is_active or locked_user.is_deleted:
        raise AccountDeletionError(
            "account_inactive",
            "This account is already inactive or cannot be closed from this session.",
            403,
        )
    user = locked_user

    existing = (
        DataSubjectRequest.query.filter(
            DataSubjectRequest.user_id == user.id,
            DataSubjectRequest.request_type == DataSubjectRequestType.DELETION,
            DataSubjectRequest.status.in_(
                (
                    DataSubjectRequestStatus.PENDING,
                    DataSubjectRequestStatus.PROCESSING,
                )
            ),
        )
        .order_by(DataSubjectRequest.id.desc())
        .first()
    )
    if existing is not None:
        grace_until = _as_aware(existing.sla_due_at) or (_now() + timedelta(days=_grace_days()))
        token = _cancellation_token(existing, user)
        return {
            "status": "scheduled",
            "message": "An account-closure request is already pending for this account.",
            "grace_until": grace_until.isoformat(),
            "cancellation_token": token,
            "cancellation_url": _cancellation_url(token),
            "request_public_id": str(existing.public_id),
        }

    # Obligation checks must run before any state change.
    from app.transport.models import Booking, DriverProfile, RideRequest
    from app.utils.enums import BookingStatus, PaymentStatus

    active_statuses = [
        getattr(BookingStatus, name)
        for name in (
            "CONFIRMED",
            "ASSIGNED",
            "DRIVER_EN_ROUTE",
            "PICKUP_ARRIVED",
            "IN_PROGRESS",
        )
        if hasattr(BookingStatus, name)
    ]
    try:
        rider_active_booking = (
            Booking.query.filter(
                Booking.user_id == user.id,
                Booking.is_deleted.is_(False),
                Booking.status.in_(active_statuses),
            ).first()
            if active_statuses else None
        )
        if rider_active_booking is not None:
            raise AccountDeletionError(
                "active_ride_pending",
                "Resolve your active ride before deleting this account. Complete "
                "or cancel the ride, then submit the deletion request again.",
                409,
            )

        searching_request = RideRequest.query.filter(
            RideRequest.user_id == user.id,
            RideRequest.is_deleted.is_(False),
            RideRequest.status.in_(("searching", "converting")),
        ).first()
        if searching_request is not None:
            raise AccountDeletionError(
                "ride_search_pending",
                "An AFCON360 ride request is still searching for a driver. Wait "
                "for it to close or cancel it before deleting this account.",
                409,
            )

        driver_profile = DriverProfile.query.filter_by(
            user_id=user.id,
            is_deleted=False,
        ).with_for_update().first()
        if driver_profile is not None:
            driver_active_booking = (
                Booking.query.filter(
                    Booking.assigned_driver_id == driver_profile.id,
                    Booking.is_deleted.is_(False),
                    Booking.status.in_(active_statuses),
                ).first()
                if active_statuses else None
            )
            if driver_active_booking is not None:
                raise AccountDeletionError(
                    "driver_trip_pending",
                    "Complete or hand over your active driver trip before deleting this account.",
                    409,
                )

            unsettled_cash = Booking.query.filter(
                Booking.booking_metadata["completed_by_driver_profile_id"].astext == str(driver_profile.id),
                Booking.status == BookingStatus.COMPLETED,
                Booking.payment_method == "cash",
                Booking.payment_status == PaymentStatus.PENDING,
                Booking.is_deleted.is_(False),
            ).first()
            if unsettled_cash is not None:
                raise AccountDeletionError(
                    "cash_receipt_pending",
                    "Confirm the cash receipt for your completed trip before "
                    "deleting this driver account.",
                    409,
                )
    except AccountDeletionError:
        raise
    except Exception as exc:
        db.session.rollback()
        logger.exception("Could not verify active transport obligations before account closure")
        raise AccountDeletionError(
            "active_service_check_unavailable",
            "AFCON360 could not verify your active rides and driver obligations. Please try again.",
            503,
        ) from exc

    _assert_no_active_accommodation_obligations(user)
    wallet_snapshot = _assert_no_financial_or_operator_obligations(user)

    open_case = _open_compliance_case(user.id)
    if open_case is not None:
        raise AccountDeletionError(
            "compliance_review_pending",
            "Your account has an open compliance review. Contact AFCON360 support "
            "before closing this account.",
            409,
        )

    now = _now()
    grace_until = now + timedelta(days=_grace_days())
    fingerprints = _closure_fingerprints(user)
    closure_state = _suppress_public_content(user, now)

    profile = None
    try:
        from app.profile.models import get_profile_by_user

        profile = get_profile_by_user(user)
    except Exception:
        logger.warning("Could not load profile for closure record", exc_info=True)

    requester_name = (
        (getattr(profile, "full_name", None) if profile else None)
        or getattr(user, "username", None)
        or "AFCON360 account holder"
    )

    closure_details = {
        "schema_version": 1,
        "surface": surface,
        "notice_version": ACCOUNT_CLOSURE_NOTICE_VERSION,
        "requested_at": now.isoformat(),
        "grace_days": _grace_days(),
        "grace_until": grace_until.isoformat(),
        "acknowledgements": {
            key: {
                "accepted": True,
                "text": REQUIRED_ACKNOWLEDGEMENTS[key],
            }
            for key in REQUIRED_ACKNOWLEDGEMENTS
        },
        "closure_fingerprint": fingerprints,
        "wallet_snapshot": wallet_snapshot,
        "content_state": closure_state,
        "ip_address": ip_address,
        "user_agent": (user_agent or "")[:512],
        "retention_summary": _RETENTION_SUMMARY,
        "legal_hold": False,
    }

    request_row = DataSubjectRequest(
        public_id=str(uuid.uuid4()),
        request_number=_request_number(now),
        request_type=DataSubjectRequestType.DELETION,
        status=DataSubjectRequestStatus.PENDING,
        user_id=user.id,
        requester_email=getattr(user, "email", None) or "",
        requester_name=requester_name,
        request_details=_json_dumps(closure_details),
        data_categories=_json_dumps(
            [
                "account_identity",
                "profile",
                "fan_profile",
                "accommodation_guest_profile",
                "accommodation_host_profile",
                "driver_profile",
                "organizer_profile",
                "feed_content",
                "media",
                "organisation_memberships",
            ]
        ),
        scope="Account closure with recoverable grace period; statutory records retained.",
        identity_verified=True,
        verification_method="password+totp" if mfa_verified else "password",
        verified_at=now,
        legal_basis="Account-holder request; applicable data-protection obligations",
        exemption_applied=False,
        exemption_reason=None,
        sla_due_at=grace_until,
        created_by=user.id,
    )

    try:
        db.session.add(request_row)

        # Revoke sessions inside the same transaction so a failed request does
        # not sign the holder out or partially suppress their content.
        mobile_session_ids = _revoke_user_sessions(
            user,
            now,
            "account_closure_requested",
        )

        user.is_active = False
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.exception("Account-closure request persistence failed")
        raise AccountDeletionError(
            "account_deletion_failed",
            "AFCON360 could not record the account-closure request. Please contact support.",
            503,
        ) from exc

    _mark_mobile_sessions_revoked(mobile_session_ids)

    token = _cancellation_token(request_row, user)
    cancel_url = _cancellation_url(token)

    try:
        from app.audit.comprehensive_audit import AuditService

        AuditService.security(
            event_type="account_closure_requested",
            severity="WARNING",
            description=f"User {user.public_id} requested account closure (grace period)",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data={
                "client_surface": surface,
                "request_public_id": str(request_row.public_id),
                "request_number": request_row.request_number,
                "notice_version": ACCOUNT_CLOSURE_NOTICE_VERSION,
                "grace_until": grace_until.isoformat(),
                "active_device_sessions_revoked": len(mobile_session_ids),
                "wallet_snapshot": wallet_snapshot,
                "legal_evidence_retained": True,
            },
        )
    except Exception:
        logger.exception("Account closure recorded but audit event delivery failed")

    emailed = _send_closure_email(user, grace_until, cancel_url)

    return {
        "status": "scheduled",
        "message": (
            "Your account is disabled and scheduled for closure on "
            f"{grace_until.date().isoformat()}. Direct profile identifiers are "
            "anonymized at closure. KYC, wallet, booking, safety, dispute and "
            "audit records required by law may be retained. Use the cancellation "
            "link before that date to restore sign-in."
        ),
        "grace_until": grace_until.isoformat(),
        "cancellation_token": token,
        "cancellation_url": cancel_url,
        "request_public_id": str(request_row.public_id),
        "request_number": request_row.request_number,
        "email_sent": emailed,
        "retention_summary": _RETENTION_SUMMARY,
    }


def cancel_account_closure(token: str) -> dict:
    """Cancel a pending closure using its signed, time-limited link."""
    if not token:
        raise AccountDeletionError(
            "cancellation_link_invalid",
            "This cancellation link is invalid.",
            400,
        )

    try:
        payload = _serializer().loads(
            token,
            max_age=366 * 86400,
        )
    except SignatureExpired as exc:
        raise AccountDeletionError(
            "cancellation_link_expired",
            "This cancellation link has expired. Contact AFCON360 support.",
            410,
        ) from exc
    except BadSignature as exc:
        raise AccountDeletionError(
            "cancellation_link_invalid",
            "This cancellation link is invalid.",
            400,
        ) from exc

    request_public_id = str(payload.get("request") or "")
    user_public_id = str(payload.get("user") or "")
    if not request_public_id or not user_public_id:
        raise AccountDeletionError(
            "cancellation_link_invalid",
            "This cancellation link is invalid.",
            400,
        )

    from app.admin.compliance.models import (
        DataSubjectRequest,
        DataSubjectRequestStatus,
        DataSubjectRequestType,
    )
    from app.identity.models.user import User

    request_row = (
        DataSubjectRequest.query.filter_by(
            public_id=request_public_id,
            request_type=DataSubjectRequestType.DELETION,
        )
        .with_for_update(of=DataSubjectRequest)
        .first()
    )
    if request_row is None:
        raise AccountDeletionError(
            "closure_request_not_found",
            "This account-closure request could not be found.",
            404,
        )

    user = (
        User.query.filter_by(
            id=request_row.user_id,
            public_id=user_public_id,
        )
        .with_for_update(of=User)
        .first()
    )
    if user is None:
        raise AccountDeletionError(
            "cancellation_link_invalid",
            "This cancellation link does not match the closure request.",
            400,
        )

    now = _now()
    if request_row.status == DataSubjectRequestStatus.COMPLETED or getattr(user, "is_deleted", False):
        raise AccountDeletionError(
            "closure_already_completed",
            "This account has already been closed and cannot be restored through this link.",
            409,
        )
    if request_row.status == DataSubjectRequestStatus.PROCESSING:
        raise AccountDeletionError(
            "closure_processing",
            "This account closure is already being finalized. Contact AFCON360 support.",
            409,
        )
    if request_row.status == DataSubjectRequestStatus.REJECTED:
        return {
            "status": "cancelled",
            "message": "This account-closure request was already cancelled.",
            "request_public_id": str(request_row.public_id),
        }

    grace_until = _as_aware(request_row.sla_due_at)
    if grace_until is None or now >= grace_until:
        raise AccountDeletionError(
            "closure_grace_period_expired",
            "The account-closure grace period has ended. Contact AFCON360 support.",
            410,
        )

    details = _parse_json(request_row.request_details)
    try:
        _restore_public_content(details.get("content_state") or {}, now)
        user.is_active = True
        request_row.status = DataSubjectRequestStatus.REJECTED
        request_row.rejection_reason = "Cancelled by the account holder during the grace period."
        request_row.completed_at = now
        request_row.response_data = _json_dumps(
            {
                "outcome": "cancelled_by_account_holder",
                "cancelled_at": now.isoformat(),
            }
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.exception("Account-closure cancellation failed")
        raise AccountDeletionError(
            "cancellation_failed",
            "AFCON360 could not cancel the closure request. Contact support.",
            503,
        ) from exc

    try:
        from app.audit.comprehensive_audit import AuditService

        AuditService.security(
            event_type="account_closure_cancelled",
            severity="INFO",
            description=f"User {user.public_id} cancelled account closure during grace period",
            user_id=user.id,
            extra_data={
                "request_public_id": str(request_row.public_id),
                "request_number": request_row.request_number,
            },
        )
    except Exception:
        logger.exception("Closure cancelled but audit event delivery failed")

    return {
        "status": "cancelled",
        "message": "Your account closure was cancelled and sign-in has been restored.",
        "request_public_id": str(request_row.public_id),
    }


def _scrub_closure_request_record(request_row, details: dict, now: datetime) -> None:
    """Remove requester identifiers and the recoverable pre-closure snapshot."""
    acknowledgements = details.get("acknowledgements") or {}
    safe_details = {
        "schema_version": details.get("schema_version", 1),
        "notice_version": details.get("notice_version"),
        "requested_at": details.get("requested_at"),
        "grace_days": details.get("grace_days"),
        "grace_until": details.get("grace_until"),
        "acknowledgements": acknowledgements,
        "finalized_at": now.isoformat(),
        "outcome": "completed",
    }

    # Keyed identity matching is retained only when explicitly enabled with a
    # dedicated key after a separate privacy/legal approval.
    if _fingerprint_enabled() and _fingerprint_pepper():
        fingerprints = details.get("closure_fingerprint")
        if isinstance(fingerprints, dict):
            safe_details["closure_fingerprint"] = fingerprints

    request_row.requester_email = (
        f"closed-{str(request_row.public_id)}@anonymized.invalid"
    )
    request_row.requester_name = "Closed account"
    request_row.request_details = _json_dumps(safe_details)
    request_row.scope = (
        "Account closure completed; direct requester identifiers and the "
        "recoverable pre-closure snapshot have been anonymized."
    )


def finalize_account_closure(request_row, details: dict | None = None) -> dict:
    """Permanently anonymize a due closure and close the request record.

    The request row is locked for the full transaction. PROCESSING is not
    committed separately: a failure rolls back to PENDING so the scheduler can
    retry it instead of leaving an unprocessable row behind.
    """
    from app.admin.compliance.models import (
        DataSubjectRequest,
        DataSubjectRequestStatus,
    )
    from app.identity.models.user import User

    request_id = getattr(request_row, "id", None)
    locked_request = (
        DataSubjectRequest.query.filter_by(id=request_id)
        .with_for_update(of=DataSubjectRequest)
        .first()
    )
    if locked_request is None:
        return {"missing_request": True}

    request_row = locked_request
    details = details if details is not None else _parse_json(request_row.request_details)
    now = _now()

    if request_row.status == DataSubjectRequestStatus.COMPLETED:
        return {
            "request_public_id": str(request_row.public_id),
            "already_closed": True,
        }
    if request_row.status == DataSubjectRequestStatus.REJECTED:
        return {
            "request_public_id": str(request_row.public_id),
            "cancelled": True,
        }
    if request_row.status not in (
        DataSubjectRequestStatus.PENDING,
        DataSubjectRequestStatus.PROCESSING,
    ):
        return {
            "request_public_id": str(request_row.public_id),
            "not_pending": True,
        }

    grace_until = _as_aware(request_row.sla_due_at)
    if grace_until is None or grace_until > now:
        return {
            "request_public_id": str(request_row.public_id),
            "not_due": True,
        }

    user = db.session.get(User, request_row.user_id)

    if user is None:
        _scrub_closure_request_record(request_row, details, now)
        request_row.status = DataSubjectRequestStatus.COMPLETED
        request_row.completed_at = now
        request_row.response_data = _json_dumps(
            {"outcome": "completed_without_identity_row", "finalized_at": now.isoformat()}
        )
        db.session.commit()
        return {"request_public_id": str(request_row.public_id), "identity_missing": True}

    if getattr(user, "is_deleted", False):
        _scrub_closure_request_record(request_row, details, now)
        request_row.status = DataSubjectRequestStatus.COMPLETED
        request_row.completed_at = now
        request_row.response_data = _json_dumps(
            {"outcome": "already_anonymized", "finalized_at": now.isoformat()}
        )
        db.session.commit()
        return {"request_public_id": str(request_row.public_id), "already_closed": True}

    open_case = _open_compliance_case(user.id)
    if open_case is not None:
        details["legal_hold"] = True
        details["legal_hold_reason"] = f"Open compliance case {open_case.case_number}"
        details["legal_hold_checked_at"] = now.isoformat()
        request_row.request_details = _json_dumps(details)
        request_row.sla_due_at = now + timedelta(days=_grace_days())
        request_row.status = DataSubjectRequestStatus.PENDING
        db.session.commit()
        try:
            from app.audit.comprehensive_audit import AuditService

            AuditService.security(
                event_type="account_closure_legal_hold",
                severity="WARNING",
                description=f"Account closure for {user.public_id} held by compliance case {open_case.case_number}",
                user_id=user.id,
                extra_data={"request_public_id": str(request_row.public_id)},
            )
        except Exception:
            logger.exception("Legal-hold audit event delivery failed")
        return {
            "request_public_id": str(request_row.public_id),
            "legal_hold": True,
            "case_number": open_case.case_number,
        }

    # Keep this state in the same transaction as anonymization. If anything
    # fails, rollback restores PENDING (or the prior legacy PROCESSING state).
    request_row.status = DataSubjectRequestStatus.PROCESSING

    try:
        summary, mobile_session_ids = _anonymize_identity(user, now)
        _scrub_closure_request_record(request_row, details, now)
        request_row.status = DataSubjectRequestStatus.COMPLETED
        request_row.completed_at = now
        request_row.response_data = _json_dumps(
            {
                "outcome": "completed",
                "finalized_at": now.isoformat(),
                "summary": summary,
                "retention_summary": _RETENTION_SUMMARY,
            }
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.exception("Account-closure finalization failed")
        raise AccountDeletionError(
            "closure_finalization_failed",
            "AFCON360 could not finalize the account closure. The request will be retried.",
            503,
        ) from exc

    _mark_mobile_sessions_revoked(mobile_session_ids)

    try:
        from app.audit.comprehensive_audit import AuditService

        AuditService.security(
            event_type="account_closure_completed",
            severity="WARNING",
            description=f"User {user.public_id} account closure finalized",
            user_id=user.id,
            extra_data={
                "request_public_id": str(request_row.public_id),
                "request_number": request_row.request_number,
                "summary": summary,
                "legal_evidence_retained": True,
            },
        )
    except Exception:
        logger.exception("Closure finalized but audit event delivery failed")

    return {
        "request_public_id": str(request_row.public_id),
        "finalized": True,
        "summary": summary,
    }


def finalize_due_account_closures(limit: int = 50) -> dict:
    """Finalize pending closure requests whose grace period has expired."""
    from app.admin.compliance.models import (
        DataSubjectRequest,
        DataSubjectRequestStatus,
        DataSubjectRequestType,
    )

    limit = max(1, min(int(limit), 250))
    now = _now()
    request_ids = [
        row[0]
        for row in (
            db.session.query(DataSubjectRequest.id)
            .filter(
                DataSubjectRequest.request_type == DataSubjectRequestType.DELETION,
                DataSubjectRequest.status.in_(
                    (
                        DataSubjectRequestStatus.PENDING,
                        DataSubjectRequestStatus.PROCESSING,
                    )
                ),
                DataSubjectRequest.sla_due_at.is_not(None),
                DataSubjectRequest.sla_due_at <= now,
            )
            .order_by(DataSubjectRequest.id.asc())
            .limit(limit)
            .all()
        )
    ]

    finalized = 0
    held = 0
    failed = 0
    for request_id in request_ids:
        request_row = db.session.get(DataSubjectRequest, request_id)
        if request_row is None:
            continue
        try:
            result = finalize_account_closure(request_row)
            if result.get("legal_hold"):
                held += 1
            elif result.get("finalized"):
                finalized += 1
        except Exception:
            failed += 1
            db.session.rollback()
            logger.exception(
                "Due account closure %s failed during scheduled finalization",
                request_id,
            )

    return {
        "candidates": len(request_ids),
        "finalized": finalized,
        "held": held,
        "failed": failed,
    }


def find_prior_closure_by_identifiers(
    *,
    email: str | None = None,
    phone: str | None = None,
    nin: str | None = None,
):
    """Return a completed closure record that matches any supplied identifier."""
    if not _fingerprint_enabled() or not _fingerprint_pepper():
        return None

    from sqlalchemy import or_

    from app.admin.compliance.models import (
        DataSubjectRequest,
        DataSubjectRequestStatus,
        DataSubjectRequestType,
    )

    hashes = [
        value
        for value in (
            _fingerprint("email", email),
            _fingerprint("phone", phone),
            _fingerprint("nin", nin),
        )
        if value
    ]
    if not hashes:
        return None

    # Fingerprints are stored under email/phone/nin keys, so match each key
    # explicitly rather than relying on a value appearing anywhere in the JSON.
    clauses = []
    for kind, value in (
        ("email", _fingerprint("email", email)),
        ("phone", _fingerprint("phone", phone)),
        ("nin", _fingerprint("nin", nin)),
    ):
        if value:
            clauses.append(
                DataSubjectRequest.request_details.contains(f'"{kind}":"{value}"')
            )
    if not clauses:
        return None

    return (
        DataSubjectRequest.query.filter(
            DataSubjectRequest.request_type == DataSubjectRequestType.DELETION,
            DataSubjectRequest.status == DataSubjectRequestStatus.COMPLETED,
            or_(*clauses),
        )
        .order_by(DataSubjectRequest.completed_at.desc())
        .first()
    )


def flag_returning_identity(user) -> dict | None:
    """Create a compliance case when a new account reuses a closed identity."""
    if not _fingerprint_enabled() or not _fingerprint_pepper():
        return None
    try:
        profile = None
        try:
            from app.profile.models import get_profile_by_user

            profile = get_profile_by_user(user)
        except Exception:
            logger.warning("Could not load profile for returning-identity check", exc_info=True)

        prior = find_prior_closure_by_identifiers(
            email=getattr(user, "email", None),
            phone=getattr(user, "phone", None),
            nin=getattr(profile, "id_number", None) if profile else None,
        )
        if prior is None:
            return None

        from app.admin.compliance.models import (
            ComplianceCase,
            ComplianceCasePriority,
            ComplianceCaseStatus,
            ComplianceCaseType,
        )

        now = _now()
        case_number = f"RET-ID-{now.strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
        case = ComplianceCase(
            public_id=str(uuid.uuid4()),
            case_type=ComplianceCaseType.OTHER,
            case_number=case_number,
            title="Returning identity after account closure",
            description=(
                "A new account matched a previously closed account by a keyed "
                "identifier fingerprint. Review for evasive re-registration, "
                "outstanding obligations or fraud risk."
            ),
            status=ComplianceCaseStatus.OPEN,
            priority=ComplianceCasePriority.HIGH,
            user_id=user.id,
            created_by=user.id,
        )
        db.session.add(case)
        db.session.commit()

        try:
            from app.audit.comprehensive_audit import AuditService

            AuditService.security(
                event_type="account_reopened_after_closure",
                severity="WARNING",
                description=f"New account {user.public_id} matched prior closed identity",
                user_id=user.id,
                extra_data={
                    "case_number": case_number,
                    "prior_closure_request": str(prior.public_id),
                },
            )
        except Exception:
            logger.exception("Returning-identity audit event delivery failed")

        return {"case_number": case_number, "prior_closure_request": str(prior.public_id)}
    except Exception:
        db.session.rollback()
        logger.exception("Returning-identity compliance flag failed")
        return None


def account_closure_metrics() -> dict:
    """Return the operational counts the owner dashboard needs."""
    from app.admin.compliance.models import (
        DataSubjectRequest,
        DataSubjectRequestStatus,
        DataSubjectRequestType,
    )
    from app.identity.models.user import User

    return {
        "registered_users": User.query.filter(User.is_deleted.is_(False)).count(),
        "closed_accounts": User.query.filter(User.is_deleted.is_(True)).count(),
        "accounts_in_grace": (
            DataSubjectRequest.query.filter(
                DataSubjectRequest.request_type == DataSubjectRequestType.DELETION,
                DataSubjectRequest.status == DataSubjectRequestStatus.PENDING,
            ).count()
        ),
        "closures_due": (
            DataSubjectRequest.query.filter(
                DataSubjectRequest.request_type == DataSubjectRequestType.DELETION,
                DataSubjectRequest.status == DataSubjectRequestStatus.PENDING,
                DataSubjectRequest.sla_due_at.is_not(None),
                DataSubjectRequest.sla_due_at <= _now(),
            ).count()
        ),
    }
