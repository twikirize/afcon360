# app/wallet/wallet.py
from __future__ import annotations
from decimal import Decimal, ROUND_DOWN, InvalidOperation, getcontext
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import uuid
import threading

from flask import current_app
from app.extensions import db
from app.wallet.models import Wallet, Transaction

# Money precision
getcontext().prec = 28
MONEY_QUANT = Decimal("0.01")

# Simple in-memory TTL cache for FX rates (replace with Redis in prod)
_fx_cache: Dict[str, Tuple[Decimal, datetime]] = {}
_fx_cache_lock = threading.Lock()
FX_CACHE_TTL = timedelta(seconds=300)


class FXProvider:
    """Pluggable FX provider interface. Replace get_rate with external API call or Redis-backed provider."""
    def get_rate(self, from_currency: str, to_currency: str) -> Optional[Decimal]:
        cfg = current_app.config.get("FX_RATES", {})
        try:
            rate = cfg[from_currency][to_currency]
            return Decimal(str(rate))
        except Exception:
            return None


def _cached_rate(from_currency: str, to_currency: str) -> Optional[Decimal]:
    key = f"{from_currency}:{to_currency}"
    with _fx_cache_lock:
        entry = _fx_cache.get(key)
        if entry:
            rate, ts = entry
            if datetime.utcnow() - ts < FX_CACHE_TTL:
                return rate
            else:
                del _fx_cache[key]
    provider: FXProvider = current_app.config.get("FX_PROVIDER", FXProvider())
    rate = provider.get_rate(from_currency, to_currency)
    if rate is not None:
        with _fx_cache_lock:
            _fx_cache[key] = (rate, datetime.utcnow())
    return rate


class Wallet:
    """Production wallet service."""

    def __init__(self, user_id: int):
        # Always internal BIGINT PK (users.id)
        if isinstance(user_id, str):
            raise TypeError("Wallet requires internal integer users.id, not public string")
        self.user_id = int(user_id)
        self.features = current_app.config.get("WALLET_FEATURES", {})
        self.supported_currencies = set(current_app.config.get(
            "SUPPORTED_CURRENCIES",
            ["USD", "UGX", "KES", "TZS", "NGN", "EUR", "CFA"]
        ))

    # -------------------------
    # Feature flags
    # -------------------------
    def _enabled(self, feature: str) -> bool:
        global_enabled = self.features.get("enabled", True)
        if not global_enabled:
            return False

        f = self.features.get(feature, False)
        base = bool(f.get("enabled")) if isinstance(f, dict) else bool(f)

        manual = self.features.get("manual_override", {})
        if feature in manual:
            return bool(manual[feature])

        auto = self.features.get("auto_disable", {})
        if feature in auto:
            entry = auto[feature]
            if isinstance(entry, bool):
                return not bool(entry)
            if isinstance(entry, dict):
                until = entry.get("until")
                if until:
                    try:
                        until_dt = datetime.fromisoformat(until)
                        if datetime.utcnow() < until_dt:
                            return False
                    except Exception:
                        return False
                else:
                    return False

        try:
            wallet_row = WalletModel.query.filter_by(user_id=self.user_id).first()
            if wallet_row and getattr(wallet_row, "disabled_features", None):
                df = wallet_row.disabled_features or {}
                if feature in df:
                    return not bool(df[feature])   # True in df means disabled
        except Exception:
            current_app.logger.exception("Failed to read per-user disabled_features")
            return False

        return base

    # -------------------------
    # Helpers
    # -------------------------
    def _tx_id(self) -> Optional[str]:
        return str(uuid.uuid4()) if self._enabled("transaction_ids") else None

    def _quantize(self, value: Decimal) -> Decimal:
        return value.quantize(MONEY_QUANT, rounding=ROUND_DOWN)

    def _to_decimal(self, value: Any) -> Decimal:
        try:
            return self._quantize(Decimal(str(value)))
        except (InvalidOperation, TypeError):
            raise ValueError("Invalid monetary value")

    def _validate_currency(self, currency: str) -> None:
        if currency not in self.supported_currencies:
            raise ValueError("Unsupported currency")

    # -------------------------
    # Persistence helpers
    # -------------------------
    def _get_wallet_row_for_update(self) -> WalletModel:
        q = db.session.query(WalletModel).filter_by(user_id=self.user_id)
        try:
            wallet = q.with_for_update().first()
        except Exception:
            wallet = q.first()
        if wallet:
            return wallet
        wallet = WalletModel(user_id=self.user_id)
        db.session.add(wallet)
        db.session.flush()
        return wallet

    def _record_tx(self, wallet: WalletModel, tx_type: str, amount: Decimal, currency: str,
                   client_request_id: Optional[str] = None, meta: Optional[dict] = None) -> TransactionModel:
        tx = TransactionModel(
            wallet_id=wallet.id,
            tx_id=self._tx_id(),
            client_request_id=client_request_id,
            type=tx_type,
            amount=amount,
            currency=currency,
            meta=meta or {},
            created_at=datetime.utcnow()
        )
        db.session.add(tx)
        return tx

    # -------------------------
    # FX and fees
    # -------------------------
    def _get_rate(self, from_currency: str, to_currency: str) -> Optional[Decimal]:
        if from_currency == to_currency:
            return Decimal("1.00")
        rate = _cached_rate(from_currency, to_currency)
        if rate is not None:
            return rate
        try:
            r1 = _cached_rate(from_currency, "USD")
            r2 = _cached_rate("USD", to_currency)
            if r1 and r2:
                return self._quantize(r1 * r2)
        except Exception:
            pass
        return None

    def _apply_conversion(self, from_currency: str, to_currency: str, amount: Decimal) -> Tuple[Decimal, Decimal]:
        rate = self._get_rate(from_currency, to_currency)
        if rate is None:
            raise RuntimeError("FX rate unavailable")
        converted = self._quantize(amount * rate)
        conversion_fee_pct = Decimal(str(current_app.config.get("CONVERSION_FEE_PCT", "0.00")))
        conversion_fee = self._quantize(converted * conversion_fee_pct)
        net = self._quantize(converted - conversion_fee)
        return net, conversion_fee

    # -------------------------
    # Core operations (deposit, withdraw, send)
    # -------------------------
    # ... keep your existing deposit(), withdraw(), send_to_peer(), get_balances() methods ...

    # -------------------------
    def deposit(self, amount: Any, currency: str = "USD", client_request_id: Optional[str] = None) -> Dict[str, Any]:
        if not self._enabled("deposit"):
            return {"status": "error", "message": "Deposits disabled"}
        try:
            amt = self._to_decimal(amount)
            self._validate_currency(currency)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        if client_request_id:
            existing = TransactionModel.query.filter_by(client_request_id=client_request_id).first()
            if existing:
                current_app.logger.info("Duplicate deposit request", extra={"user_id": self.user_id, "client_request_id": client_request_id})
                return {"status": "ok", "message": "Duplicate request", "tx_id": existing.tx_id or existing.id}

        try:
            with db.session.begin():
                wallet = self._get_wallet_row_for_update()
                if currency == wallet.home_currency:
                    wallet.balance_home = self._quantize(Decimal(wallet.balance_home) + amt)
                    tx_detail = "deposit_home"
                    fees = {}
                    settled_amount = amt
                    settled_currency = wallet.home_currency
                elif currency == wallet.local_currency:
                    wallet.balance_local = self._quantize(Decimal(wallet.balance_local) + amt)
                    tx_detail = "deposit_local"
                    fees = {}
                    settled_amount = amt
                    settled_currency = wallet.local_currency
                elif self._enabled("multi_currency"):
                    net, conv_fee = self._apply_conversion(currency, wallet.local_currency, amt)
                    wallet.balance_local = self._quantize(Decimal(wallet.balance_local) + net)
                    tx_detail = "deposit_conv"
                    fees = {"conversion_fee": str(conv_fee)}
                    settled_amount = net
                    settled_currency = wallet.local_currency
                else:
                    raise ValueError("Unsupported currency")

                tx_meta = {"detail": tx_detail, "fees": fees, "settled_amount": str(settled_amount), "settled_currency": settled_currency}
                self._record_tx(wallet, "deposit", amt, currency, client_request_id=client_request_id, meta=tx_meta)
            return {"status": "success", "message": "Deposit completed", "balances": self.get_balances(wallet)}
        except ValueError as e:
            current_app.logger.warning("Deposit validation failed", exc_info=True, extra={"user_id": self.user_id})
            return {"status": "error", "message": str(e)}
        except Exception:
            current_app.logger.error("Deposit failed", exc_info=True, extra={"user_id": self.user_id})
            return {"status": "error", "message": "Internal error"}

    def withdraw(self, amount: Any, currency: Optional[str] = None, client_request_id: Optional[str] = None) -> Dict[str, Any]:
        if not self._enabled("withdraw"):
            return {"status": "error", "message": "Withdrawals disabled"}
        try:
            amt = self._to_decimal(amount)
        except ValueError:
            return {"status": "error", "message": "Invalid amount"}

        try:
            with db.session.begin():
                wallet = self._get_wallet_row_for_update()
                currency = currency or wallet.local_currency
                self._validate_currency(currency)

                if currency == wallet.home_currency:
                    if Decimal(wallet.balance_home) < amt:
                        return {"status": "error", "message": "Insufficient home balance"}
                    wallet.balance_home = self._quantize(Decimal(wallet.balance_home) - amt)
                elif currency == wallet.local_currency:
                    if Decimal(wallet.balance_local) < amt:
                        return {"status": "error", "message": "Insufficient local balance"}
                    wallet.balance_local = self._quantize(Decimal(wallet.balance_local) - amt)
                else:
                    return {"status": "error", "message": "Unsupported currency"}

                self._record_tx(wallet, "withdrawal", amt, currency, client_request_id=client_request_id)
            return {"status": "success", "message": "Withdrawal completed", "balances": self.get_balances(wallet)}
        except ValueError as e:
            current_app.logger.warning("Withdraw validation failed", exc_info=True, extra={"user_id": self.user_id})
            return {"status": "error", "message": str(e)}
        except Exception:
            current_app.logger.error("Withdraw failed", exc_info=True, extra={"user_id": self.user_id})
            return {"status": "error", "message": "Internal error"}

    def send_to_peer(self, receiver_user_id: int, amount: Any, currency: Optional[str] = None,
                     platform_fee: Optional[Any] = None, client_request_id: Optional[str] = None) -> Dict[str, Any]:
        if not self._enabled("peer_send"):
            return {"status": "error", "message": "Peer sends disabled"}
        try:
            amt = self._to_decimal(amount)
            fee_amt = self._to_decimal(platform_fee) if platform_fee is not None else Decimal("0.00")
        except ValueError:
            return {"status": "error", "message": "Invalid amount or fee"}

        if client_request_id:
            existing = TransactionModel.query.filter_by(client_request_id=client_request_id).first()
            if existing:
                current_app.logger.info("Duplicate peer send", extra={"user_id": self.user_id, "client_request_id": client_request_id})
                return {"status": "ok", "message": "Duplicate request", "tx_id": existing.tx_id or existing.id}

        try:
            with db.session.begin():
                sender = self._get_wallet_row_for_update()
                q = db.session.query(WalletModel).filter_by(user_id=receiver_user_id)
                try:
                    receiver = q.with_for_update().first()
                except Exception:
                    receiver = q.first()
                if not receiver:
                    receiver = WalletModel(user_id=receiver_user_id)
                    db.session.add(receiver)
                    db.session.flush()

                currency = currency or sender.home_currency
                self._validate_currency(currency)

                total = self._quantize(amt + fee_amt)

                if currency == sender.home_currency and Decimal(sender.balance_home) < total:
                    return {"status": "error", "message": "Insufficient home balance"}
                if currency == sender.local_currency and Decimal(sender.balance_local) < total:
                    return {"status": "error", "message": "Insufficient local balance"}

                if currency == sender.home_currency:
                    sender.balance_home = self._quantize(Decimal(sender.balance_home) - total)
                else:
                    sender.balance_local = self._quantize(Decimal(sender.balance_local) - total)

                credit_amount = amt
                conversion_fee = Decimal("0.00")
                if currency != receiver.local_currency:
                    credit_amount, conversion_fee = self._apply_conversion(currency, receiver.local_currency, amt)

                receiver.balance_local = self._quantize(Decimal(receiver.balance_local) + credit_amount)

                meta_sender = {"to_user": receiver_user_id, "platform_fee": str(fee_amt), "conversion_fee": str(conversion_fee)}
                meta_receiver = {"from_user": self.user_id, "conversion_fee": str(conversion_fee)}
                self._record_tx(sender, "send", amt, currency, client_request_id=client_request_id, meta=meta_sender)
                self._record_tx(receiver, "receive", credit_amount, receiver.local_currency, meta=meta_receiver)

                # Hook: route platform_fee to fee account (double-entry ledger) - implement in ledger module
            return {"status": "success", "message": "Peer transfer completed"}
        except ValueError as e:
            current_app.logger.warning("Peer send validation failed", exc_info=True, extra={"user_id": self.user_id})
            return {"status": "error", "message": str(e)}
        except RuntimeError as e:
            current_app.logger.warning("Peer send FX failure", exc_info=True, extra={"user_id": self.user_id})
            return {"status": "error", "message": str(e)}
        except Exception:
            current_app.logger.error("Peer send failed", exc_info=True, extra={"user_id": self.user_id})
            return {"status": "error", "message": "Internal error"}

    # -------------------------
    # Read helpers
    # -------------------------
    def get_balances(self, wallet: Optional[WalletModel] = None) -> Dict[str, str]:
        wallet = wallet or WalletModel.query.filter_by(user_id=self.user_id).first()
        if not wallet:
            return {"balance_home": "0.00", "balance_local": "0.00", "home_currency": "USD", "local_currency": "UGX"}
        return {
            "balance_home": str(self._quantize(Decimal(wallet.balance_home))),
            "balance_local": str(self._quantize(Decimal(wallet.balance_local))),
            "home_currency": wallet.home_currency,
            "local_currency": wallet.local_currency
        }


# app/wallet/wallet.py method
def _enabled(self, feature: str) -> bool:
    # 1 Global emergency switch
    global_enabled = self.features.get("enabled", True)
    if not global_enabled:
        return False

    # 2 Per-feature base config
    f = self.features.get(feature, False)
    base = bool(f.get("enabled")) if isinstance(f, dict) else bool(f)

    # 3 Manual override highest priority
    manual = self.features.get("manual_override", {})
    if feature in manual:
        return bool(manual[feature])

    # 4 Auto-disable entries with optional expiry
    auto = self.features.get("auto_disable", {})
    if feature in auto:
        entry = auto[feature]
        if isinstance(entry, bool):
            return not bool(entry)
        if isinstance(entry, dict):
            until = entry.get("until")
            if until:
                try:
                    from datetime import datetime
                    until_dt = datetime.fromisoformat(until)
                    if datetime.utcnow() < until_dt:
                        return False
                except Exception:
                    return False
            else:
                return False

    # 5 Per-user disabled_features JSON column
    try:
        wallet_row = WalletModel.query.filter_by(user_id=self.user_id).first()
        if wallet_row and getattr(wallet_row, "disabled_features", None):
            df = wallet_row.disabled_features or {}
            if feature in df:
                return not bool(df[feature])   # True in df means disabled
    except Exception:
        current_app.logger.exception("Failed to read per-user disabled_features")
        return False

    # 6 Default to base
    return base

