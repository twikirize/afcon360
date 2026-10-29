"""
Wallet-owned marketplace invoice/payment-intent contract.

Transport and other marketplace modules may create an obligation and report
service lifecycle facts. They must not debit wallets, call provider gateways,
record cash as received, or mark an invoice paid directly.
"""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.wallet.models.marketplace_invoice import MarketplaceInvoice

logger = logging.getLogger(__name__)

# This is a Wallet-owned integration capability registry, not a transport
# allowlist. A configured method remains unavailable until its marketplace
# collection/verification lifecycle is implemented here.
_MARKETPLACE_COLLECTION_METHODS = frozenset({"cash", "wallet"})
_SUPPORTED_SETTLEMENT_TIMINGS = frozenset({"pay_on_completion"})
_MONEY_QUANTUM = Decimal("0.01")
_SETTLED_STATES = frozenset({"paid", "cash_received"})


class MarketplaceInvoiceError(Exception):
    """Stable, safe error from the Wallet marketplace invoice boundary."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _money(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(
            _MONEY_QUANTUM, rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MarketplaceInvoiceError("invalid_amount", "Invoice amount is invalid") from exc
    if not amount.is_finite() or amount <= 0:
        raise MarketplaceInvoiceError("invalid_amount", "Invoice amount must be greater than zero")
    return amount


def _currency(value: Any) -> str:
    result = str(value or "").strip().upper()
    if not result or len(result) > 10 or not result.isalpha():
        raise MarketplaceInvoiceError("invalid_currency", "Invoice currency is invalid")
    return result


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


class MarketplaceInvoiceService:
    """Wallet boundary for marketplace collection, receipt and settlement."""

    @staticmethod
    def _method_config(
        method_id: str,
        *,
        currency: str,
        amount: Decimal,
        settlement_timing: str,
        service_country_code: Optional[str] = None,
    ):
        from app.wallet.models.payment_method import PaymentMethodConfig

        method_id = str(method_id or "").strip().lower()
        if method_id not in _MARKETPLACE_COLLECTION_METHODS:
            raise MarketplaceInvoiceError(
                "method_not_integrated",
                "This payment method is not yet integrated for marketplace settlement.",
            )
        config = PaymentMethodConfig.query.filter_by(
            method_id=method_id,
            is_enabled=True,
            is_active=True,
        ).first()
        if config is None:
            raise MarketplaceInvoiceError(
                "method_unavailable",
                "This payment method is not enabled in Wallet configuration.",
            )
        if not config.supports_currency(currency):
            raise MarketplaceInvoiceError(
                "currency_not_supported",
                "Wallet has not enabled this payment method for the quoted currency.",
            )
        timings = {
            str(item).strip().lower()
            for item in (config.allowed_timings or [])
        }
        if settlement_timing not in timings:
            raise MarketplaceInvoiceError(
                "timing_not_supported",
                "Wallet has not enabled this payment method for pay-on-completion.",
            )
        if service_country_code:
            service_country_code = str(service_country_code).strip().upper()
            if config.country_code and str(config.country_code).upper() != service_country_code:
                raise MarketplaceInvoiceError(
                    "market_not_supported",
                    "This payment method is not configured for the service market.",
                )
        minimum = Decimal(str(config.min_amount or 0))
        maximum = Decimal(str(config.max_amount)) if config.max_amount is not None else None
        if amount < minimum or (maximum is not None and amount > maximum):
            raise MarketplaceInvoiceError(
                "amount_out_of_range",
                "The quoted amount is outside the configured limits for this payment method.",
            )
        return config

    @staticmethod
    def _wallet_account_available(payer_user_id: Optional[int], currency: str) -> bool:
        if payer_user_id is None:
            return False
        from app.wallet.models.ledger import AccountModel

        accounts = AccountModel.query.filter_by(
            user_id=payer_user_id,
            owner_type="user",
            currency=currency,
        ).all()
        return any(
            _status_value(account.status) == "active"
            and not bool(account.is_frozen)
            for account in accounts
        )

    @classmethod
    def list_available_methods(
        cls,
        *,
        payer_user_id: Optional[int],
        currency: str,
        amount: Optional[Any] = None,
        settlement_timing: str = "pay_on_completion",
        service_country_code: Optional[str] = None,
        payer_country_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List only methods Wallet can actually settle for these invoice terms.

        Payer country is carried as context for future provider eligibility;
        it is intentionally not inferred from nationality. At present only
        Wallet balance and cash have implemented marketplace settlement paths.
        """
        try:
            normalized_currency = _currency(currency)
            timing = str(settlement_timing or "").strip().lower()
            if timing not in _SUPPORTED_SETTLEMENT_TIMINGS:
                return []
            quote_amount = _money(amount) if amount is not None else None

            from app.wallet.models.payment_method import PaymentMethodConfig

            configs = PaymentMethodConfig.query.filter_by(
                is_enabled=True, is_active=True,
            ).all()
            available = []
            for config in configs:
                method_id = str(config.method_id or "").strip().lower()
                if method_id not in _MARKETPLACE_COLLECTION_METHODS:
                    continue
                if not config.supports_currency(normalized_currency):
                    continue
                if timing not in {
                    str(item).strip().lower()
                    for item in (config.allowed_timings or [])
                }:
                    continue
                if service_country_code and str(config.country_code or "").upper() != str(service_country_code).upper():
                    continue
                if quote_amount is not None:
                    minimum = Decimal(str(config.min_amount or 0))
                    maximum = Decimal(str(config.max_amount)) if config.max_amount is not None else None
                    if quote_amount < minimum or (maximum is not None and quote_amount > maximum):
                        continue
                if method_id == "wallet" and not cls._wallet_account_available(
                    payer_user_id, normalized_currency
                ):
                    continue

                category = {
                    "cash": "offline",
                    "wallet": "digital",
                }.get(method_id, "digital")
                available.append({
                    "code": method_id,
                    "label": config.display_name,
                    "default": method_id == "cash",
                    "category": category,
                    "gateway": config.provider_name if config.provider_name != "afcon360" else None,
                    "description": (
                        f"{config.display_name} in {normalized_currency}; "
                        "settled after trip completion."
                    ),
                    "metadata": {
                        "currency": normalized_currency,
                        "settlement_timing": timing,
                        "service_country_code": service_country_code,
                        "payer_country_code": payer_country_code,
                    },
                })
            available.sort(key=lambda item: (not item["default"], item["label"].lower()))
            return available
        except MarketplaceInvoiceError:
            return []
        except Exception:
            # Configuration problems must hide methods, never cause a fallback
            # to a transport-owned catalogue or pretend cash is available.
            logger.exception("Wallet marketplace method eligibility failed closed")
            return []

    @staticmethod
    def get_invoice(invoice_id: Any, *, for_update: bool = False) -> MarketplaceInvoice:
        try:
            parsed_id = uuid.UUID(str(invoice_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise MarketplaceInvoiceError("invoice_not_found", "Wallet invoice not found") from exc
        query = MarketplaceInvoice.query.filter_by(id=parsed_id)
        if for_update:
            query = query.with_for_update()
        invoice = query.first()
        if invoice is None:
            raise MarketplaceInvoiceError("invoice_not_found", "Wallet invoice not found")
        return invoice

    @staticmethod
    def find_invoice(
        service_code: str,
        service_reference: str,
        *,
        for_update: bool = False,
    ) -> Optional[MarketplaceInvoice]:
        query = MarketplaceInvoice.query.filter_by(
            service_code=str(service_code or "").strip().lower(),
            service_reference=str(service_reference or "").strip(),
        )
        if for_update:
            query = query.with_for_update()
        return query.first()

    @staticmethod
    def _immutable_terms_match(
        invoice: MarketplaceInvoice,
        *,
        service_code: str,
        service_reference: str,
        payer_user_id: int,
        amount: Decimal,
        currency: str,
        payment_method: str,
        settlement_timing: str,
        service_country_code: Optional[str],
        payer_country_code: Optional[str],
    ) -> bool:
        return (
            invoice.service_code == service_code
            and invoice.service_reference == service_reference
            and int(invoice.payer_user_id) == int(payer_user_id)
            and Decimal(str(invoice.amount)).quantize(_MONEY_QUANTUM) == amount
            and str(invoice.currency).upper() == currency
            and str(invoice.payment_method).lower() == payment_method
            and str(invoice.settlement_timing).lower() == settlement_timing
            and invoice.service_country_code == service_country_code
            and invoice.payer_country_code == payer_country_code
        )

    @classmethod
    def create_invoice(
        cls,
        *,
        idempotency_key: str,
        service_code: str,
        service_reference: str,
        payer_user_id: int,
        amount: Any,
        currency: str,
        payment_method: str,
        settlement_timing: str = "pay_on_completion",
        service_country_code: Optional[str] = None,
        payer_country_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> MarketplaceInvoice:
        """Create or replay one Wallet-owned invoice without moving money."""
        key = str(idempotency_key or "").strip()
        code = str(service_code or "").strip().lower()
        reference = str(service_reference or "").strip()
        method = str(payment_method or "").strip().lower()
        timing = str(settlement_timing or "").strip().lower()
        normalized_currency = _currency(currency)
        normalized_amount = _money(amount)
        service_country = (
            str(service_country_code).strip().upper() if service_country_code else None
        )
        payer_country = (
            str(payer_country_code).strip().upper() if payer_country_code else None
        )
        if not key or len(key) > 255:
            raise MarketplaceInvoiceError("invalid_idempotency_key", "Wallet invoice idempotency key is invalid")
        if not code or len(code) > 50 or not reference or len(reference) > 255:
            raise MarketplaceInvoiceError("invalid_service_reference", "Marketplace service reference is invalid")
        if payer_user_id is None:
            raise MarketplaceInvoiceError("payer_required", "A payer is required for this invoice")
        if timing not in _SUPPORTED_SETTLEMENT_TIMINGS:
            raise MarketplaceInvoiceError("timing_not_supported", "Wallet does not support this settlement timing")

        existing = MarketplaceInvoice.query.filter_by(idempotency_key=key).first()
        if existing is None:
            existing = MarketplaceInvoice.query.filter_by(
                service_code=code, service_reference=reference,
            ).first()
        if existing is not None:
            if not cls._immutable_terms_match(
                existing,
                service_code=code,
                service_reference=reference,
                payer_user_id=payer_user_id,
                amount=normalized_amount,
                currency=normalized_currency,
                payment_method=method,
                settlement_timing=timing,
                service_country_code=service_country,
                payer_country_code=payer_country,
            ):
                raise MarketplaceInvoiceError(
                    "invoice_idempotency_conflict",
                    "This marketplace reference already has a Wallet invoice with different terms.",
                )
            return existing

        cls._method_config(
            method,
            currency=normalized_currency,
            amount=normalized_amount,
            settlement_timing=timing,
            service_country_code=service_country,
        )
        if method == "wallet" and not cls._wallet_account_available(
            payer_user_id, normalized_currency
        ):
            raise MarketplaceInvoiceError(
                "wallet_account_missing",
                "A Wallet account in the quoted currency is required for this payment method.",
            )

        invoice = MarketplaceInvoice(
            idempotency_key=key,
            service_code=code,
            service_reference=reference,
            payer_user_id=int(payer_user_id),
            amount=normalized_amount,
            currency=normalized_currency,
            payment_method=method,
            settlement_timing=timing,
            service_country_code=service_country,
            payer_country_code=payer_country,
            status="pending",
            invoice_metadata=dict(metadata or {}),
            receipt_metadata={},
        )
        db.session.add(invoice)
        db.session.flush()
        if commit:
            db.session.commit()
        return invoice

    @classmethod
    def _validate_context(
        cls,
        invoice: MarketplaceInvoice,
        *,
        service_code: str,
        service_reference: str,
        payer_user_id: int,
        amount: Any,
        currency: str,
    ) -> None:
        normalized_amount = _money(amount)
        normalized_currency = _currency(currency)
        if (
            invoice.service_code != str(service_code or "").strip().lower()
            or invoice.service_reference != str(service_reference or "").strip()
            or int(invoice.payer_user_id) != int(payer_user_id)
            or Decimal(str(invoice.amount)).quantize(_MONEY_QUANTUM) != normalized_amount
            or str(invoice.currency).upper() != normalized_currency
        ):
            raise MarketplaceInvoiceError(
                "invoice_context_mismatch",
                "The settlement details do not match the confirmed Wallet invoice.",
            )

    @classmethod
    def mark_due_after_completion(
        cls,
        *,
        invoice_id: Any,
        payer_user_id: int,
        service_code: str,
        service_reference: str,
        amount: Any,
        currency: str,
    ) -> MarketplaceInvoice:
        """Record the service-completion fact. This does not mean it was paid."""
        invoice = cls.get_invoice(invoice_id, for_update=True)
        cls._validate_context(
            invoice,
            service_code=service_code,
            service_reference=service_reference,
            payer_user_id=payer_user_id,
            amount=amount,
            currency=currency,
        )
        if invoice.status == "pending":
            invoice.status = "due"
            invoice.due_at = datetime.now(timezone.utc)
            db.session.add(invoice)
            db.session.commit()
            return invoice
        if invoice.status in {"due", "paid", "cash_received"}:
            return invoice
        raise MarketplaceInvoiceError(
            "invoice_not_payable",
            "This Wallet invoice is not payable in its current state.",
        )

    @classmethod
    def settle_after_completion(
        cls,
        *,
        invoice_id: Any,
        payer_user_id: int,
        service_code: str,
        service_reference: str,
        amount: Any,
        currency: str,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Settle a completed service through Wallet, idempotently.

        At present this executes the Wallet-balance collection path only. Other
        digital methods remain unavailable until Wallet has a real provider
        initiation, verification, and callback lifecycle for marketplace invoices.
        """
        invoice = cls.mark_due_after_completion(
            invoice_id=invoice_id,
            payer_user_id=payer_user_id,
            service_code=service_code,
            service_reference=service_reference,
            amount=amount,
            currency=currency,
        )
        if invoice.status in _SETTLED_STATES:
            return {
                "invoice_id": str(invoice.id),
                "status": invoice.status,
                "transaction_id": str(invoice.transaction_id) if invoice.transaction_id else None,
                "already_processed": True,
            }
        if invoice.payment_method == "cash":
            return {
                "invoice_id": str(invoice.id),
                "status": "due",
                "transaction_id": None,
                "requires_cash_receipt_confirmation": True,
            }
        if invoice.payment_method != "wallet":
            raise MarketplaceInvoiceError(
                "method_not_integrated",
                "This payment method cannot yet settle a marketplace invoice.",
            )

        from app.wallet.exceptions import (
            InsufficientBalanceError,
            WalletNotFoundError,
        )
        from app.wallet.models.transaction import TransactionModel
        from app.wallet.services.wallet_service import WalletService

        wallet_service = WalletService()
        account = wallet_service.account_repo.get_by_user_id(
            invoice.payer_user_id, invoice.currency
        )
        if account is None or str(account.currency).upper() != invoice.currency:
            raise MarketplaceInvoiceError(
                "wallet_account_missing",
                "No Wallet account exists in the invoice currency.",
            )

        # The Wallet transaction idempotency key is derived from the immutable
        # invoice UUID, so retrying after a worker/request failure cannot debit
        # the rider twice.
        wallet_key = "MARKETPLACE-INVOICE-" + str(invoice.id)
        try:
            result = wallet_service.withdraw(
                account_id=str(account.id),
                amount=Decimal(str(invoice.amount)),
                currency=invoice.currency,
                client_request_id=wallet_key,
                metadata={
                    "marketplace_invoice_id": str(invoice.id),
                    "service_code": invoice.service_code,
                    "service_reference": invoice.service_reference,
                    "settlement_timing": invoice.settlement_timing,
                    "request_id": request_id,
                },
                payment_method="wallet",
                payment_provider="afcon360_wallet",
                actor_id=invoice.payer_user_id,
                system_initiated=True,
            )
        except InsufficientBalanceError as exc:
            # Invoice stays due. A rider can top up and retry; there is no
            # fabricated paid status and no second invoice.
            raise MarketplaceInvoiceError(
                "insufficient_funds",
                "Your Wallet balance is too low. Add funds, then retry payment.",
            ) from exc
        except WalletNotFoundError as exc:
            raise MarketplaceInvoiceError(
                "wallet_account_missing",
                "No Wallet account exists in the invoice currency.",
            ) from exc
        except Exception as exc:
            logger.exception("Wallet collection failed for marketplace invoice %s", invoice.id)
            raise MarketplaceInvoiceError(
                "settlement_unavailable",
                "Wallet could not complete settlement. The invoice remains due and can be retried.",
            ) from exc

        if not isinstance(result, dict) or result.get("status") != "success" or not result.get("transaction_id"):
            raise MarketplaceInvoiceError(
                "settlement_unverified",
                "Wallet did not return a completed transaction reference.",
            )
        try:
            transaction_id = uuid.UUID(str(result["transaction_id"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise MarketplaceInvoiceError(
                "settlement_unverified",
                "Wallet returned an invalid transaction reference.",
            ) from exc

        transaction = TransactionModel.query.filter_by(id=transaction_id).first()
        if (
            transaction is None
            or _status_value(transaction.status) != "completed"
            or Decimal(str(transaction.amount)).quantize(_MONEY_QUANTUM)
            != Decimal(str(invoice.amount)).quantize(_MONEY_QUANTUM)
            or str(transaction.currency).upper() != invoice.currency
            or (transaction.user_id is not None and int(transaction.user_id) != int(invoice.payer_user_id))
        ):
            raise MarketplaceInvoiceError(
                "settlement_unverified",
                "Wallet's canonical transaction does not match this invoice.",
            )

        # WalletService commits its canonical transaction before returning.
        # Re-lock the invoice and mark it paid only after verifying that record.
        invoice = cls.get_invoice(invoice.id, for_update=True)
        if invoice.status == "paid":
            if invoice.transaction_id != transaction_id:
                raise MarketplaceInvoiceError(
                    "invoice_already_paid",
                    "This invoice has already been settled by a different transaction.",
                )
            return {
                "invoice_id": str(invoice.id),
                "status": "paid",
                "transaction_id": str(invoice.transaction_id),
                "already_processed": True,
            }
        if invoice.status != "due":
            raise MarketplaceInvoiceError(
                "invoice_state_changed",
                "The Wallet invoice changed state during settlement; reconcile before retrying.",
            )
        invoice.status = "paid"
        invoice.transaction_id = transaction_id
        invoice.provider_reference = str(transaction_id)
        invoice.paid_at = datetime.now(timezone.utc)
        invoice.invoice_metadata = {
            **(invoice.invoice_metadata or {}),
            "settlement_request_id": request_id,
        }
        db.session.add(invoice)
        db.session.commit()
        return {
            "invoice_id": str(invoice.id),
            "status": "paid",
            "transaction_id": str(transaction_id),
            "already_processed": False,
        }

    @classmethod
    def confirm_cash_receipt(
        cls,
        *,
        invoice_id: Any,
        payer_user_id: int,
        service_code: str,
        service_reference: str,
        amount: Any,
        currency: str,
        driver_user_id: int,
        driver_profile_id: int,
        driver_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Wallet-owned receipt record for cash collected directly by a driver."""
        from app.wallet.models.audit import AuditLogModel

        invoice = cls.get_invoice(invoice_id, for_update=True)
        cls._validate_context(
            invoice,
            service_code=service_code,
            service_reference=service_reference,
            payer_user_id=payer_user_id,
            amount=amount,
            currency=currency,
        )
        if invoice.payment_method != "cash":
            raise MarketplaceInvoiceError(
                "method_mismatch",
                "This invoice did not select cash payment.",
            )

        receipt = dict(invoice.receipt_metadata or {})
        if invoice.status == "cash_received":
            if int(receipt.get("driver_profile_id") or -1) == int(driver_profile_id):
                return {
                    "invoice_id": str(invoice.id),
                    "status": "cash_received",
                    "already_processed": True,
                }
            raise MarketplaceInvoiceError(
                "cash_already_confirmed",
                "Cash receipt has already been confirmed for this invoice.",
            )
        if invoice.status != "due":
            raise MarketplaceInvoiceError(
                "invoice_not_due",
                "Cash can be confirmed only after Wallet records the completed trip as due.",
            )

        now = datetime.now(timezone.utc)
        invoice.status = "cash_received"
        invoice.cash_received_at = now
        invoice.cash_received_by_user_id = int(driver_user_id)
        invoice.receipt_metadata = {
            "driver_user_id": int(driver_user_id),
            "driver_profile_id": int(driver_profile_id),
            "driver_code": str(driver_code or "")[:100] or None,
            "confirmed_at": now.isoformat(),
            "amount": str(invoice.amount),
            "currency": invoice.currency,
            "service_reference": invoice.service_reference,
            "collection_channel": "direct_cash_to_driver",
        }
        db.session.add(AuditLogModel(
            actor_id=int(driver_user_id),
            action="marketplace_cash_receipt_confirmed",
            description="Driver confirmed direct cash receipt for a completed marketplace service.",
            before_state={"invoice_id": str(invoice.id), "status": "due"},
            after_state={
                "invoice_id": str(invoice.id),
                "status": "cash_received",
                "driver_profile_id": int(driver_profile_id),
                "amount": str(invoice.amount),
                "currency": invoice.currency,
            },
            request_id=invoice.idempotency_key,
        ))
        db.session.commit()
        return {
            "invoice_id": str(invoice.id),
            "status": "cash_received",
            "already_processed": False,
        }
