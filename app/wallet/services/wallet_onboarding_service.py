"""Explicit customer Wallet onboarding and read-only account lookup.

No user Wallet is ever opened by lookup, page rendering, payment initiation,
payouts or provider callbacks. A customer Wallet can be created only after
terms acceptance, verified-country resolution and owner-approved currency
validation. USD is only the platform FX reference currency.
"""
from __future__ import annotations

from typing import Any, Optional

from app.extensions import db


class WalletOnboardingError(ValueError):
    """A customer Wallet opening request failed a business/security gate."""


def _load_user(user_ref: Any):
    from app.identity.models.user import User

    if user_ref is None:
        return None
    if hasattr(user_ref, "id") and getattr(user_ref, "id", None) is not None:
        return db.session.get(User, int(user_ref.id))
    if isinstance(user_ref, str):
        return User.query.filter_by(public_id=user_ref.strip()).first()
    try:
        return db.session.get(User, int(user_ref))
    except (TypeError, ValueError):
        return None


def get_user_wallet_account(user_ref: Any, currency: Optional[str] = None):
    """Read an existing USER wallet; never create one.

    With a currency, only an exact denomination is returned. Without one,
    the oldest account is the user's primary/home Wallet.
    """
    from app.wallet.models.ledger import AccountModel, AccountOwnerType

    user = _load_user(user_ref)
    if user is None:
        return None

    query = AccountModel.query.filter_by(
        user_id=int(user.id),
        owner_type=AccountOwnerType.USER.value,
    )
    if currency not in (None, ""):
        query = query.filter_by(currency=str(currency).strip().upper())
    return query.order_by(
        AccountModel.created_at.asc(),
        AccountModel.id.asc(),
    ).first()


def create_user_wallet_account(
    user_ref: Any,
    *,
    currency: Any,
    terms_accepted: bool,
):
    """Create the first customer Wallet in an explicit, approved currency.

    The function flushes but does not commit: the caller owns the database
    transaction and any related onboarding audit/tracker records.
    Returns (account, already_exists) for safe retries.
    """
    from datetime import datetime, timezone

    from app.identity.models.user import User
    from app.wallet.models.ledger import (
        AccountModel,
        AccountOwnerType,
        AccountStatus,
        AccountType,
    )
    from app.wallet.services.home_currency_service import resolve_home_currency

    if terms_accepted is not True:
        raise WalletOnboardingError(
            "Accept the AFCON360 Wallet terms before opening your Wallet."
        )

    user = _load_user(user_ref)
    if user is None or not user.is_active or user.is_deleted:
        raise WalletOnboardingError("This AFCON360 account is not available.")
    if not bool(getattr(user, "email_verified", False)):
        raise WalletOnboardingError(
            "Verify your email address before opening an AFCON360 Wallet."
        )

    # Validates the proven residence/registration country, Wallet capability,
    # user-selected denomination and country-specific currency restrictions.
    selected_currency = resolve_home_currency(
        user,
        requested_currency=currency,
    )

    # The caller may already have a read transaction from bearer auth,
    # currency resolution or wallet-creation tracking. Do not commit or roll
    # it back here: the row lock and new account remain in the caller's unit
    # of work until that caller commits or rolls back.
    locked_user = (
        db.session.query(User)
        .filter_by(id=int(user.id))
        .with_for_update()
        .one_or_none()
    )
    if locked_user is None or not locked_user.is_active or locked_user.is_deleted:
        raise WalletOnboardingError("This AFCON360 account is not available.")
    if not bool(getattr(locked_user, "email_verified", False)):
        raise WalletOnboardingError(
            "Verify your email address before opening an AFCON360 Wallet."
        )

    existing = (
        db.session.query(AccountModel)
        .filter_by(
            user_id=int(locked_user.id),
            owner_type=AccountOwnerType.USER.value,
        )
        .order_by(AccountModel.created_at.asc(), AccountModel.id.asc())
        .with_for_update()
        .first()
    )
    if existing is not None:
        existing_currency = str(existing.currency or "").strip().upper()
        if existing_currency == selected_currency:
            return existing, True
        raise WalletOnboardingError(
            f"Your first Wallet is already denominated in {existing_currency}. "
            "AFCON360 will not silently replace it or open a second wallet."
        )

    now = datetime.now(timezone.utc)
    account = AccountModel(
        user_id=int(locked_user.id),
        owner_type=AccountOwnerType.USER.value,
        account_type=AccountType.USER_WALLET.value,
        status=AccountStatus.ACTIVE.value,
        currency=selected_currency,
        account_name=f"Wallet_{selected_currency}_{int(locked_user.id)}",
        is_frozen=False,
        verified=False,
        terms_accepted_at=now,
    )
    db.session.add(account)
    db.session.flush()
    return account, False
