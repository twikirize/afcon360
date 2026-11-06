"""Bearer-authenticated customer wallet withdrawals.

The first provider route is deliberately limited to Uganda UGX mobile-money
payouts. A withdrawal reserves wallet value before contacting the provider,
stays pending until independently confirmed, and is reversed exactly once on
a verified provider failure. Destination details are encrypted at rest.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from flask import current_app, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db
from app.wallet.models.config import PaymentProviderConfig, WalletSystemConfig
from app.wallet.models.ledger import AccountModel, EntryType, LedgerEntryModel
from app.wallet.models.transaction import TransactionModel, TransactionStatus, TransactionType
from app.wallet.models.audit import AuditLogModel
from app.wallet.repositories.ledger_repository import LedgerRepository
from app.wallet.services.wallet_service import WalletService


class NativeWithdrawalError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NativeWithdrawalService:
    PROVIDER = "flutterwave"
    CURRENCY = "UGX"
    QUOTE_MAX_AGE_SECONDS = 300
    SUPPORTED_UG_NETWORKS = {"MTN", "AIRTEL"}
    FLOW_VERSION = 1

    @staticmethod
    def _serializer():
        secret = current_app.secret_key
        if not secret:
            raise NativeWithdrawalError(
                "withdrawal_unavailable",
                "AFCON360 cannot securely prepare a withdrawal right now.",
                503,
            )
        return URLSafeTimedSerializer(
            secret_key=secret,
            salt="afcon360-native-wallet-withdrawal-quote-v1",
        )

    @staticmethod
    def _encrypt_destination(phone: str, beneficiary_name: str) -> str:
        # Do not use encrypt_field(): it intentionally falls back to plaintext
        # for legacy callers. Payout destinations must fail closed.
        from app.utils.security import _get_fernet

        raw = f"{phone}\n{beneficiary_name}".encode("utf-8")
        return _get_fernet().encrypt(raw).decode("ascii")

    @staticmethod
    def _decrypt_destination(ciphertext: str) -> tuple[str, str]:
        from app.utils.security import _get_fernet

        try:
            raw = _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
            phone, name = raw.split("\n", 1)
            return phone, name
        except Exception as exc:
            current_app.logger.exception("Native withdrawal destination could not be decrypted")
            raise NativeWithdrawalError(
                "withdrawal_destination_unavailable",
                "The saved payout destination cannot be accessed safely. Contact AFCON360 support.",
                503,
            ) from exc

    @staticmethod
    def _normalise_uganda_phone(value: str) -> str:
        raw = str(value or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) == 10 and digits.startswith("0"):
            digits = "256" + digits[1:]
        if not re.fullmatch(r"256\d{9}", digits):
            raise NativeWithdrawalError(
                "withdrawal_phone_invalid",
                "Enter a valid Ugandan mobile number, including its country code.",
                400,
            )
        return digits

    @staticmethod
    def _mask_phone(phone: str) -> str:
        return f"+256 *** ***{phone[-3:]}"

    @classmethod
    def _ensure_provider_ready(cls):
        config = PaymentProviderConfig.get_active_config(cls.PROVIDER)
        env_secret = current_app.config.get("FLUTTERWAVE_SECRET_KEY")
        if not env_secret and not (config and config.secret_key):
            raise NativeWithdrawalError(
                "withdrawal_provider_unavailable",
                "The payout provider is not configured for withdrawals.",
                503,
            )
        if config is not None and (not config.is_enabled or not config.is_active):
            raise NativeWithdrawalError(
                "withdrawal_provider_unavailable",
                "The payout provider is currently disabled.",
                503,
            )

    @classmethod
    def create_quote(
        cls,
        user,
        *,
        amount,
        currency: str,
        network: str,
        phone_number: str,
        beneficiary_name: str,
    ) -> dict:
        cls._ensure_provider_ready()

        currency = str(currency or "").strip().upper()
        network = str(network or "").strip().upper()
        if currency != cls.CURRENCY:
            raise NativeWithdrawalError(
                "withdrawal_currency_unsupported",
                "The current native payout route supports UGX withdrawals only.",
                400,
            )
        if network not in cls.SUPPORTED_UG_NETWORKS:
            raise NativeWithdrawalError(
                "withdrawal_network_unsupported",
                "Choose MTN or Airtel Mobile Money for a Ugandan UGX withdrawal.",
                400,
            )

        phone = cls._normalise_uganda_phone(phone_number)
        name = " ".join(str(beneficiary_name or "").split())
        if len(name) < 2 or len(name) > 100 or not any(ch.isalpha() for ch in name):
            raise NativeWithdrawalError(
                "withdrawal_beneficiary_invalid",
                "Enter the beneficiary's full name.",
                400,
            )

        try:
            payout_amount = Decimal(str(amount))
            if not payout_amount.is_finite() or payout_amount <= 0:
                raise ValueError("invalid")
            if payout_amount != payout_amount.to_integral_value():
                raise ValueError("UGX payout amounts must be whole shillings")
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise NativeWithdrawalError(
                "withdrawal_amount_invalid",
                "Enter a positive whole-number amount in UGX.",
                400,
            ) from exc

        config = WalletSystemConfig.get_config()
        if not config.withdrawals_enabled:
            raise NativeWithdrawalError(
                "withdrawals_disabled",
                "Wallet withdrawals are temporarily unavailable.",
                503,
            )

        maximum = Decimal(str(config.max_withdrawal_amount or "0"))
        if maximum > 0 and payout_amount > maximum:
            raise NativeWithdrawalError(
                "withdrawal_limit_exceeded",
                f"The maximum withdrawal is {maximum:,.0f} UGX.",
                400,
            )

        fee_percent = Decimal(str(config.withdrawal_fee_percent or "0"))
        if fee_percent < 0 or fee_percent > 100:
            raise NativeWithdrawalError(
                "withdrawal_fee_configuration_invalid",
                "The configured withdrawal fee is invalid. Contact AFCON360 support.",
                503,
            )
        platform_fee = (payout_amount * fee_percent / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_debit = payout_amount + platform_fee

        account = AccountModel.query.filter_by(
            user_id=user.id,
            owner_type="user",
            currency=cls.CURRENCY,
        ).first()
        if account is None or str(account.status).lower() != "active":
            raise NativeWithdrawalError(
                "wallet_not_found",
                "You do not have an active UGX wallet.",
                404,
            )
        if account.is_frozen:
            raise NativeWithdrawalError(
                "wallet_frozen",
                "Your wallet is restricted. Contact AFCON360 support.",
                403,
            )

        wallet = WalletService()
        try:
            wallet._check_kyc_limits(
                int(user.id),
                total_debit,
                "withdraw",
                cls.CURRENCY,
                account_id=str(account.id),
            )
        except Exception as exc:
            raise NativeWithdrawalError(
                "withdrawal_compliance_blocked",
                str(exc),
                403,
            ) from exc

        balance = LedgerRepository().get_balance(account.id, cls.CURRENCY)
        if balance < total_debit:
            raise NativeWithdrawalError(
                "insufficient_balance",
                "Your UGX wallet does not have enough available funds for the withdrawal and fee.",
                402,
            )

        quote_id = uuid4().hex
        now = datetime.now(timezone.utc)
        ciphertext = cls._encrypt_destination(phone, name)
        payload = {
            "version": cls.FLOW_VERSION,
            "quote_id": quote_id,
            "user_public_id": str(user.public_id),
            "account_id": str(account.id),
            "amount": str(payout_amount),
            "fee_amount": str(platform_fee),
            "fee_percent": str(fee_percent),
            "total_debit": str(total_debit),
            "currency": cls.CURRENCY,
            "network": network,
            "destination_ciphertext": ciphertext,
            "destination_masked": cls._mask_phone(phone),
            "beneficiary_name": name,
            "provider": cls.PROVIDER,
            "issued_at": now.isoformat(),
        }
        quote_token = cls._serializer().dumps(payload)
        return {
            "quote_id": quote_id,
            "quote_token": quote_token,
            "amount": str(payout_amount),
            "currency": cls.CURRENCY,
            "network": network,
            "beneficiary_name": name,
            "masked_phone": cls._mask_phone(phone),
            "platform_fee": str(platform_fee),
            "fee_percent": str(fee_percent),
            "total_wallet_debit": str(total_debit),
            "available_balance": str(balance),
            "expires_at": (now + timedelta(seconds=cls.QUOTE_MAX_AGE_SECONDS)).isoformat(),
            "provider_fee": "Paid separately by AFCON360; not added to the quoted wallet debit.",
        }

    @classmethod
    def _load_quote(cls, user, quote_token: str) -> dict:
        try:
            payload = cls._serializer().loads(
                str(quote_token or ""),
                max_age=cls.QUOTE_MAX_AGE_SECONDS,
            )
        except SignatureExpired as exc:
            raise NativeWithdrawalError(
                "withdrawal_quote_expired",
                "This withdrawal quote has expired. Request a new quote.",
                409,
            ) from exc
        except BadSignature as exc:
            raise NativeWithdrawalError(
                "withdrawal_quote_invalid",
                "This withdrawal quote is invalid. Request a new quote.",
                400,
            ) from exc
        if (
            payload.get("version") != cls.FLOW_VERSION
            or payload.get("provider") != cls.PROVIDER
            or payload.get("user_public_id") != str(user.public_id)
            or payload.get("currency") != cls.CURRENCY
        ):
            raise NativeWithdrawalError(
                "withdrawal_quote_invalid",
                "This withdrawal quote does not belong to this account.",
                403,
            )
        return payload

    @classmethod
    def _reference_for_quote(cls, user, quote_id: str) -> str:
        digest = hashlib.sha256(
            f"{user.public_id}:{quote_id}".encode("utf-8")
        ).hexdigest()[:48].upper()
        return f"NATWD-{digest}"

    @staticmethod
    def _public_transaction_data(tx: TransactionModel) -> dict:
        metadata = tx.tx_metadata or {}
        return {
            "reference": tx.client_request_id,
            "status": str(getattr(tx.status, "value", tx.status)).lower(),
            "amount": str(metadata.get("payout_amount") or tx.amount),
            "currency": str(tx.currency).upper(),
            "platform_fee": str(metadata.get("fee_amount") or tx.fee_amount or "0"),
            "total_wallet_debit": str(metadata.get("total_wallet_debit") or tx.amount),
            "network": metadata.get("network"),
            "beneficiary_name": metadata.get("beneficiary_name"),
            "masked_phone": metadata.get("destination_masked"),
            "provider": tx.payment_provider,
            "provider_status": metadata.get("provider_status"),
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
            "completed_at": tx.completed_at.isoformat() if tx.completed_at else None,
            "failure_reason": tx.failure_reason,
            "manual_review_required": bool(metadata.get("manual_review_required")),
        }

    @classmethod
    def confirm_quote(cls, user, *, quote_token: str, pin: str) -> dict:
        cls._ensure_provider_ready()
        quote = cls._load_quote(user, quote_token)
        reference = cls._reference_for_quote(user, quote["quote_id"])

        # A quote can produce exactly one withdrawal. Retrying the same quote
        # returns the existing state instead of submitting another payout.
        db.session.rollback()
        existing = TransactionModel.query.filter_by(
            client_request_id=reference,
            user_id=user.id,
        ).first()
        if existing:
            if (existing.tx_metadata or {}).get("quote_id") != quote["quote_id"]:
                raise NativeWithdrawalError(
                    "withdrawal_idempotency_conflict",
                    "This withdrawal reference has already been used.",
                    409,
                )
            return cls._public_transaction_data(existing)

        payout_amount = Decimal(quote["amount"])
        fee_amount = Decimal(quote["fee_amount"])
        total_debit = Decimal(quote["total_debit"])
        pin_error = None
        reserved_tx = None
        created_reservation = False

        db.session.rollback()
        try:
            with db.session.begin():
                # Check again after acquiring locks; this is the idempotency gate
                # for two simultaneous confirmation requests using one quote.
                existing = (
                    db.session.query(TransactionModel)
                    .filter_by(client_request_id=reference)
                    .with_for_update()
                    .one_or_none()
                )
                if existing:
                    if (
                        int(existing.user_id or 0) != int(user.id)
                        or (existing.tx_metadata or {}).get("quote_id") != quote["quote_id"]
                    ):
                        raise NativeWithdrawalError(
                            "withdrawal_idempotency_conflict",
                            "This withdrawal reference has already been used.",
                            409,
                        )
                    reserved_tx = existing
                else:
                    from app.identity.models.user import User

                    locked_user = (
                        db.session.query(User)
                        .filter_by(id=user.id)
                        # User has joined-eager optional relationships. Lock
                        # only the users row; locking the nullable outer-join
                        # sides is rejected by PostgreSQL.
                        .with_for_update(of=User)
                        .one_or_none()
                    )
                    if locked_user is None or not locked_user.is_active or locked_user.is_deleted:
                        raise NativeWithdrawalError(
                            "account_unavailable",
                            "This AFCON360 account is not available.",
                            403,
                        )
                    if not locked_user.transaction_pin_hash:
                        pin_error = NativeWithdrawalError(
                            "transaction_pin_not_set",
                            "Set a transaction PIN before withdrawing money.",
                            403,
                        )
                    elif not pin or not locked_user.verify_transaction_pin(str(pin), session=db.session):
                        # Commit the failed-attempt counter by exiting this
                        # transaction normally; do not reserve or debit funds.
                        pin_error = NativeWithdrawalError(
                            "transaction_pin_invalid",
                            "Your transaction PIN is incorrect or locked.",
                            403,
                        )

                    if pin_error is None:
                        account = (
                            db.session.query(AccountModel)
                            .filter_by(
                                id=quote["account_id"],
                                user_id=user.id,
                                owner_type="user",
                                currency=cls.CURRENCY,
                            )
                            .with_for_update()
                            .one_or_none()
                        )
                        if account is None or str(account.status).lower() != "active":
                            raise NativeWithdrawalError(
                                "wallet_not_found",
                                "Your UGX wallet is not available.",
                                404,
                            )
                        if account.is_frozen:
                            raise NativeWithdrawalError(
                                "wallet_frozen",
                                "Your wallet is restricted. Contact AFCON360 support.",
                                403,
                            )

                        config = WalletSystemConfig.get_config()
                        if not config.withdrawals_enabled:
                            raise NativeWithdrawalError(
                                "withdrawals_disabled",
                                "Wallet withdrawals are temporarily unavailable.",
                                503,
                            )
                        if str(config.withdrawal_fee_percent or "0") != quote["fee_percent"]:
                            raise NativeWithdrawalError(
                                "withdrawal_quote_stale",
                                "The withdrawal fee changed. Request a new quote before confirming.",
                                409,
                            )
                        maximum = Decimal(str(config.max_withdrawal_amount or "0"))
                        if maximum > 0 and payout_amount > maximum:
                            raise NativeWithdrawalError(
                                "withdrawal_limit_exceeded",
                                "The withdrawal amount is now above the configured limit. Request a new quote.",
                                409,
                            )

                        wallet = WalletService(db.session)
                        wallet._check_kyc_limits(
                            int(user.id),
                            total_debit,
                            "withdraw",
                            cls.CURRENCY,
                            account_id=str(account.id),
                        )
                        wallet._check_fraud_risk(
                            int(user.id),
                            total_debit,
                            cls.CURRENCY,
                            ip_address=getattr(request, "remote_addr", None),
                        )
                        wallet._check_daily_limit(account.id, total_debit, cls.CURRENCY, "withdraw")
                        wallet._check_monthly_limit(account.id, total_debit, cls.CURRENCY)

                        ledger = LedgerRepository(db.session)
                        balance_before = ledger.get_balance(account.id, cls.CURRENCY)
                        if balance_before < total_debit:
                            raise NativeWithdrawalError(
                                "insufficient_balance",
                                "Your available UGX balance has changed. Request a new quote.",
                                402,
                            )

                        metadata = {
                            "native_withdrawal_version": cls.FLOW_VERSION,
                            "payout_state": "submission_started",
                            "quote_id": quote["quote_id"],
                            "payout_amount": str(payout_amount),
                            "fee_amount": str(fee_amount),
                            "fee_percent": quote["fee_percent"],
                            "total_wallet_debit": str(total_debit),
                            "network": quote["network"],
                            "destination_masked": quote["destination_masked"],
                            "destination_ciphertext": quote["destination_ciphertext"],
                            "beneficiary_name": quote["beneficiary_name"],
                            "provider": cls.PROVIDER,
                            "provider_status": "not_submitted",
                        }
                        reserved_tx = TransactionModel(
                            client_request_id=reference,
                            tx_type=TransactionType.WITHDRAW,
                            status=TransactionStatus.PENDING,
                            amount=total_debit,
                            currency=cls.CURRENCY,
                            user_id=user.id,
                            account_id=account.id,
                            external_reference=reference,
                            payment_provider=cls.PROVIDER,
                            payment_method="mobile_money",
                            fee_amount=fee_amount,
                            fee_currency=cls.CURRENCY,
                            tx_metadata=metadata,
                        )
                        db.session.add(reserved_tx)
                        db.session.flush()
                        created_reservation = True

                        db.session.add(
                            LedgerEntryModel(
                                transaction_id=reserved_tx.id,
                                account_id=account.id,
                                entry_type=EntryType.DEBIT,
                                amount=total_debit,
                                currency=cls.CURRENCY,
                                meta={
                                    "purpose": "native_withdrawal_reservation",
                                    "reference": reference,
                                },
                            )
                        )
                        wallet.account_repo.update_volume(account.id, total_debit, "daily")
                        audit = AuditLogModel(
                            transaction_id=reserved_tx.id,
                            actor_id=user.id,
                            action="withdrawal_reserved",
                            description=f"Reserved {total_debit} {cls.CURRENCY} for a pending mobile-money payout",
                            before_state={"balance": str(balance_before)},
                            after_state={"balance": str(balance_before - total_debit)},
                            ip_address=getattr(request, "remote_addr", None),
                            user_agent=(request.user_agent.string if request and request.user_agent else None),
                            audit_metadata={
                                "reference": reference,
                                "network": quote["network"],
                                "destination_masked": quote["destination_masked"],
                                "payout_amount": str(payout_amount),
                                "fee_amount": str(fee_amount),
                            },
                        )
                        db.session.add(audit)
        except NativeWithdrawalError:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception("Native wallet withdrawal reservation failed for %s", user.public_id)
            raise NativeWithdrawalError(
                "withdrawal_reservation_failed",
                "AFCON360 could not safely reserve the withdrawal. Your wallet was not charged.",
                503,
            ) from exc

        if pin_error is not None:
            raise pin_error

        # A duplicate confirmation can arrive while the first request is
        # contacting Flutterwave. Only the request that created the reservation
        # may submit the provider transfer.
        if not created_reservation:
            return cls._public_transaction_data(reserved_tx)

        phone, name = cls._decrypt_destination(quote["destination_ciphertext"])
        from app.wallet.services.payment_gateway import (
            PaymentOrchestrator,
            PaymentProvider,
            PayoutRequest,
        )

        try:
            response = PaymentOrchestrator().initiate_withdrawal(
                PayoutRequest(
                    amount=int(payout_amount),
                    currency=cls.CURRENCY,
                    user_id=int(user.id),
                    recipient_name=name,
                    recipient_account=phone,
                    recipient_bank_code=quote["network"],
                    recipient_phone=phone,
                    provider=PaymentProvider.FLUTTERWAVE,
                    reason="AFCON360 wallet withdrawal",
                    reference=reference,
                )
            )
        except Exception:
            # The provider may have accepted the request before the network
            # failed. Keep funds reserved and require status/webhook reconciliation.
            current_app.logger.exception("Flutterwave withdrawal submission outcome is unknown for %s", reference)
            cls._update_provider_state(reference, {
                "payout_state": "submission_unknown",
                "provider_status": "unknown",
                "manual_review_required": True,
            })
            db.session.rollback()
            tx = TransactionModel.query.filter_by(client_request_id=reference, user_id=user.id).first()
            return cls._public_transaction_data(tx)

        if response.success:
            provider_reference = str(response.provider_reference or "").strip()
            provider_status = str(response.status or "pending").lower()
            cls._update_provider_state(reference, {
                "provider_reference": provider_reference or None,
                "provider_status": provider_status,
                "payout_state": "processing" if provider_status not in {"failed", "error"} else "submission_unknown",
                "manual_review_required": not bool(provider_reference),
            })
            if provider_status in {"successful", "completed"}:
                cls._finish_success(
                    reference,
                    cls.PROVIDER,
                    {
                        "reference": reference,
                        "id": provider_reference,
                        "amount": str(response.amount or payout_amount),
                        "currency": str(response.currency or cls.CURRENCY),
                    },
                )
            elif provider_status == "failed":
                cls._finish_failure(
                    reference,
                    cls.PROVIDER,
                    "Flutterwave rejected the payout.",
                    {
                        "reference": reference,
                        "amount": str(payout_amount),
                        "currency": cls.CURRENCY,
                    },
                )
        elif str(response.status or "").lower() == "failed":
            cls._finish_failure(
                reference,
                cls.PROVIDER,
                str(response.message or "Flutterwave rejected the payout."),
                {
                    "reference": reference,
                    "amount": str(payout_amount),
                    "currency": cls.CURRENCY,
                },
            )
        else:
            cls._update_provider_state(reference, {
                "payout_state": "submission_unknown",
                "provider_status": str(response.status or "unknown").lower(),
                "manual_review_required": True,
            })

        db.session.rollback()
        tx = TransactionModel.query.filter_by(client_request_id=reference, user_id=user.id).first()
        return cls._public_transaction_data(tx)

    @classmethod
    def _update_provider_state(cls, reference: str, values: dict):
        db.session.rollback()
        try:
            with db.session.begin():
                tx = (
                    db.session.query(TransactionModel)
                    .filter_by(client_request_id=reference)
                    .with_for_update()
                    .one_or_none()
                )
                if not tx or tx.tx_type != TransactionType.WITHDRAW:
                    return
                metadata = dict(tx.tx_metadata or {})
                if metadata.get("native_withdrawal_version") != cls.FLOW_VERSION:
                    return
                metadata.update(values)
                tx.tx_metadata = metadata
                if values.get("provider_reference"):
                    tx.external_reference = str(values["provider_reference"])
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Could not update payout provider state for %s", reference)

    @classmethod
    def _validate_provider_payload(cls, tx: TransactionModel, provider: str, payload: dict):
        metadata = tx.tx_metadata or {}
        if metadata.get("native_withdrawal_version") != cls.FLOW_VERSION:
            raise NativeWithdrawalError("withdrawal_not_found", "Withdrawal request not found.", 404)
        if provider != tx.payment_provider:
            raise NativeWithdrawalError("withdrawal_provider_mismatch", "Payout provider does not match the withdrawal.", 409)
        if str(payload.get("reference") or "") != tx.client_request_id:
            raise NativeWithdrawalError("withdrawal_reference_mismatch", "Payout reference does not match the withdrawal.", 409)
        if str(payload.get("currency") or "").upper() != str(tx.currency).upper():
            raise NativeWithdrawalError("withdrawal_currency_mismatch", "Payout currency does not match the withdrawal.", 409)
        try:
            actual = Decimal(str(payload.get("amount")))
            expected = Decimal(str(metadata.get("payout_amount")))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise NativeWithdrawalError("withdrawal_amount_unverified", "The provider did not return a verifiable payout amount.", 409) from exc
        if actual != expected:
            raise NativeWithdrawalError("withdrawal_amount_mismatch", "Payout amount does not match the confirmed withdrawal.", 409)
        provider_id = str(payload.get("id") or "").strip()
        stored_provider_id = str(metadata.get("provider_reference") or "").strip()
        if stored_provider_id and provider_id and stored_provider_id != provider_id:
            raise NativeWithdrawalError("withdrawal_provider_reference_mismatch", "Provider transfer ID does not match this withdrawal.", 409)

    @classmethod
    def _finish_success(cls, reference: str, provider: str, payload: dict):
        db.session.rollback()
        try:
            with db.session.begin():
                tx = (
                    db.session.query(TransactionModel)
                    .filter_by(client_request_id=reference)
                    .with_for_update()
                    .one_or_none()
                )
                if not tx:
                    raise NativeWithdrawalError("withdrawal_not_found", "Withdrawal request not found.", 404)
                if tx.status == TransactionStatus.COMPLETED:
                    return
                if tx.status != TransactionStatus.PENDING:
                    raise NativeWithdrawalError("withdrawal_terminal_state", "This withdrawal is already in a final state.", 409)
                cls._validate_provider_payload(tx, provider, payload)
                metadata = dict(tx.tx_metadata or {})
                metadata.update({
                    "payout_state": "completed",
                    "provider_status": "successful",
                    "provider_reference": str(payload.get("id") or metadata.get("provider_reference") or ""),
                    "manual_review_required": False,
                })
                tx.tx_metadata = metadata
                tx.status = TransactionStatus.COMPLETED
                tx.completed_at = datetime.now(timezone.utc)
        except NativeWithdrawalError:
            db.session.rollback()
            raise
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Could not complete native payout %s", reference)
            raise

    @classmethod
    def _finish_failure(cls, reference: str, provider: str, reason: str, payload: dict):
        db.session.rollback()
        try:
            with db.session.begin():
                tx = (
                    db.session.query(TransactionModel)
                    .filter_by(client_request_id=reference)
                    .with_for_update()
                    .one_or_none()
                )
                if not tx:
                    raise NativeWithdrawalError("withdrawal_not_found", "Withdrawal request not found.", 404)
                if tx.status == TransactionStatus.FAILED:
                    return
                if tx.status == TransactionStatus.COMPLETED:
                    # A late failure event must never reverse a payout already
                    # independently confirmed successful.
                    raise NativeWithdrawalError("withdrawal_terminal_state", "A completed payout cannot be automatically reversed.", 409)
                if tx.status != TransactionStatus.PENDING:
                    raise NativeWithdrawalError("withdrawal_terminal_state", "This withdrawal is already in a final state.", 409)
                cls._validate_provider_payload(tx, provider, payload)

                metadata = dict(tx.tx_metadata or {})
                total_debit = Decimal(str(metadata.get("total_wallet_debit") or tx.amount))
                account = db.session.query(AccountModel).filter_by(id=tx.account_id).with_for_update().one()
                balance_before = LedgerRepository(db.session).get_balance(account.id, tx.currency)

                reversal_reference = f"{tx.client_request_id}-REV"
                existing_reversal = (
                    db.session.query(TransactionModel)
                    .filter_by(client_request_id=reversal_reference)
                    .with_for_update()
                    .one_or_none()
                )
                if existing_reversal is None:
                    reversal = TransactionModel(
                        client_request_id=reversal_reference,
                        tx_type=TransactionType.REFUND,
                        status=TransactionStatus.COMPLETED,
                        amount=total_debit,
                        currency=tx.currency,
                        user_id=tx.user_id,
                        account_id=tx.account_id,
                        external_reference=tx.client_request_id,
                        payment_provider=provider,
                        payment_method="withdrawal_reversal",
                        tx_metadata={
                            "source": "native_withdrawal_reversal",
                            "original_reference": tx.client_request_id,
                            "reason": str(reason)[:500],
                        },
                        completed_at=datetime.now(timezone.utc),
                    )
                    db.session.add(reversal)
                    db.session.flush()
                    db.session.add(
                        LedgerEntryModel(
                            transaction_id=reversal.id,
                            account_id=account.id,
                            entry_type=EntryType.CREDIT,
                            amount=total_debit,
                            currency=tx.currency,
                            meta={
                                "purpose": "native_withdrawal_reversal",
                                "original_reference": tx.client_request_id,
                            },
                        )
                    )
                    balance_after = balance_before + total_debit
                    db.session.add(
                        AuditLogModel(
                            transaction_id=reversal.id,
                            actor_id=tx.user_id,
                            action="withdrawal_reversed",
                            description=f"Reversed failed withdrawal {tx.client_request_id}",
                            before_state={"balance": str(balance_before)},
                            after_state={"balance": str(balance_after)},
                            audit_metadata={
                                "original_reference": tx.client_request_id,
                                "reversal_reference": reversal_reference,
                            },
                        )
                    )
                metadata.update({
                    "payout_state": "failed",
                    "provider_status": "failed",
                    "failure_reason": str(reason)[:500],
                    "reversal_reference": reversal_reference,
                    "manual_review_required": False,
                })
                tx.tx_metadata = metadata
                tx.status = TransactionStatus.FAILED
                tx.failed_at = datetime.now(timezone.utc)
                tx.failure_reason = str(reason)[:500]
        except NativeWithdrawalError:
            db.session.rollback()
            raise
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Could not reverse failed native payout %s", reference)
            raise

    @classmethod
    def handle_provider_event(cls, reference: str, provider: str, payload: dict):
        data = payload or {}
        status = str(data.get("status") or "").strip().lower()
        if status in {"successful", "completed", "success"}:
            cls._finish_success(reference, provider, data)
        elif status in {"failed", "failure"}:
            cls._finish_failure(
                reference,
                provider,
                str(data.get("complete_message") or "The payout provider reported failure."),
                data,
            )
        else:
            cls._update_provider_state(reference, {
                "provider_status": status or "unknown",
                "payout_state": "processing",
            })

    @classmethod
    def get_status(cls, user, reference: str) -> dict:
        db.session.rollback()
        tx = TransactionModel.query.filter_by(
            client_request_id=str(reference),
            user_id=user.id,
            tx_type=TransactionType.WITHDRAW,
        ).first()
        if tx is None or (tx.tx_metadata or {}).get("native_withdrawal_version") != cls.FLOW_VERSION:
            raise NativeWithdrawalError("withdrawal_not_found", "Withdrawal request not found.", 404)

        metadata = tx.tx_metadata or {}
        if tx.status == TransactionStatus.PENDING and metadata.get("provider_reference"):
            from app.wallet.services.payment_gateway import PaymentOrchestrator, PaymentProvider

            try:
                response = PaymentOrchestrator().verify_withdrawal(
                    PaymentProvider.FLUTTERWAVE,
                    str(metadata["provider_reference"]),
                )
                provider_status = str(response.status or "").lower()
                provider_payload = {
                    "reference": reference,
                    "id": response.provider_reference,
                    "amount": str(response.amount) if response.amount is not None else None,
                    "currency": str(response.currency or ""),
                }
                if provider_status in {"successful", "completed", "success"}:
                    cls._finish_success(reference, cls.PROVIDER, provider_payload)
                elif provider_status in {"failed", "failure"}:
                    cls._finish_failure(
                        reference,
                        cls.PROVIDER,
                        str(response.message or "Flutterwave reported a failed payout."),
                        provider_payload,
                    )
                else:
                    cls._update_provider_state(reference, {
                        "provider_status": provider_status or "unknown",
                        "payout_state": "processing",
                    })
            except NativeWithdrawalError:
                raise
            except Exception:
                current_app.logger.exception("Payout status verification unavailable for %s", reference)
                # Verification failure is not proof of payout failure; funds stay reserved.
            db.session.rollback()
            tx = TransactionModel.query.filter_by(
                client_request_id=str(reference),
                user_id=user.id,
                tx_type=TransactionType.WITHDRAW,
            ).first()
        return cls._public_transaction_data(tx)
