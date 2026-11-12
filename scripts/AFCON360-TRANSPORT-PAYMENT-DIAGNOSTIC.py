"""Read-only AFCON360 Transport payment readiness diagnostic.

Run from the AFCON360 project root with the project's .venv Python.
This script refuses to inspect any database other than afcon360_test.
It does not enable methods, change configuration, create payments, or write rows.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

# Force the dedicated preview overlay for this process only.
os.environ["APP_ENV"] = "phone-preview"
os.environ["FLASK_ENV"] = "development"
os.environ["FLASK_DEBUG"] = "false"


def money(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def masked_email(value: str | None) -> str:
    if not value or "@" not in value:
        return "(not displayed)"
    local, domain = value.split("@", 1)
    prefix = local[:1] if local else "*"
    return f"{prefix}***@{domain}"


def main() -> int:
    print("\n========== AFCON360 TRANSPORT PAYMENT READINESS ==========")
    print("MODE: READ ONLY — no configuration changes or payments will be made")

    try:
        from app import create_app
        app = create_app()
    except Exception as exc:
        print(f"ERROR: Could not initialise AFCON360: {type(exc).__name__}: {exc}")
        return 2

    with app.app_context():
        from sqlalchemy import func, text
        from sqlalchemy.engine import make_url
        from app.extensions import db
        from app.identity.models.user import User
        from app.wallet.models.payment_method import PaymentMethodConfig
        from app.wallet.services.wallet_service import WalletService

        uri = app.config.get("SQLALCHEMY_DATABASE_URI")
        if not uri:
            print("STOP: Application has no configured database URI.")
            return 3
        configured_db = make_url(uri).database
        print(f"APP_ENV: {app.config.get('APP_ENV')}")
        print(f"FLASK_ENV: {app.config.get('FLASK_ENV')}")
        print(f"CONFIGURED DATABASE: {configured_db}")
        if configured_db != "afcon360_test":
            print("STOP: This diagnostic is restricted to afcon360_test.")
            return 4

        try:
            with db.engine.connect() as conn:
                db_name, db_role, db_timezone = conn.execute(text(
                    "SELECT current_database(), current_user, current_setting('TimeZone')"
                )).one()
        except Exception as exc:
            print(f"STOP: Database verification failed: {type(exc).__name__}: {exc}")
            return 5

        print(f"CONNECTED DATABASE: {db_name}")
        print(f"DATABASE ROLE: {db_role}")
        print(f"SESSION TIMEZONE: {db_timezone}")
        if db_name != "afcon360_test" or str(db_timezone).upper() != "UTC":
            print("STOP: Database name or timezone failed the safety check.")
            return 6
        print("DATABASE SAFETY: PASS")

        who = input("\nRider test-account email or internal numeric user ID: ").strip()
        if not who:
            print("STOP: A rider test account is required for user-specific readiness.")
            return 7
        if who.isdigit():
            user = db.session.get(User, int(who))
        else:
            user = User.query.filter(func.lower(User.email) == who.lower()).first()
        if user is None:
            print("STOP: No matching rider account was found in afcon360_test.")
            return 8

        currency = input("Fare currency shown by the selected quote (e.g. UGX or USD): ").strip().upper()
        if not currency:
            print("STOP: Fare currency is required.")
            return 9
        amount_raw = input("Exact fare amount shown for that quote: ").strip().replace(",", "")
        amount = money(amount_raw)
        if amount is None or amount <= 0:
            print("STOP: Enter a valid positive fare amount.")
            return 10

        # Keep this aligned with the native endpoint's current request.
        timing = "pay_on_completion"
        print("\n========== FARE TERMS ==========")
        print(f"RIDER INTERNAL ID: {user.id}")
        print(f"RIDER ACCOUNT: {masked_email(getattr(user, 'email', None))}")
        print(f"FARE: {currency} {amount}")
        print(f"SETTLEMENT TIMING REQUESTED BY NATIVE API: {timing}")

        configs = PaymentMethodConfig.query.order_by(PaymentMethodConfig.method_id).all()
        print("\n========== OWNER PAYMENT-METHOD CONFIGURATION ==========")
        print("The following fields control whether a method is considered for Transport:")
        print("enabled | active | marketplace collection implemented | currency | timing | amount limits")

        by_code = {}
        for config in configs:
            code = str(config.method_id or "").strip().lower()
            by_code[code] = config
            enabled = bool(config.is_enabled)
            active = bool(config.is_active)
            implemented = bool(getattr(config, "marketplace_collection_implemented", False))
            currencies = [str(x).upper() for x in (config.supported_currencies or [])]
            timings = [str(x).strip().lower() for x in (config.allowed_timings or [])]
            min_amount = money(config.min_amount) or Decimal("0")
            max_amount = money(config.max_amount)
            reasons = []
            if not enabled:
                reasons.append("disabled globally (is_enabled=false)")
            if not active:
                reasons.append("inactive (is_active=false)")
            if not implemented:
                reasons.append("Wallet marketplace collection is not marked implemented")
            if currency not in currencies:
                reasons.append(f"currency {currency} is not in supported_currencies")
            if timing not in timings:
                reasons.append(f"timing {timing} is missing from allowed_timings")
            if amount < min_amount:
                reasons.append(f"fare is below min_amount {min_amount}")
            if max_amount is not None and amount > max_amount:
                reasons.append(f"fare exceeds max_amount {max_amount}")
            eligible_by_config = not reasons
            print(f"\nMETHOD: {code or '(blank)'} — {config.display_name}")
            print(f"  enabled={enabled}; active={active}; marketplace_collection_implemented={implemented}")
            print(f"  supported_currencies={currencies}")
            print(f"  allowed_timings={timings}")
            print(f"  amount_range={min_amount} .. {max_amount if max_amount is not None else 'unbounded'}")
            print(f"  CONFIG GATE: {'PASS' if eligible_by_config else 'BLOCKED'}")
            for reason in reasons:
                print(f"    - {reason}")

        if not configs:
            print("NO payment_method_configs rows exist in this database.")

        print("\n========== WALLET CERTIFICATION RESULT ==========")
        try:
            statuses = WalletService().get_user_payment_method_status(
                user_id=user.id,
                currency=currency,
                amount=amount,
                settlement_timing=timing,
            )
        except Exception as exc:
            db.session.rollback()
            print(f"CERTIFICATION ERROR: {type(exc).__name__}: {exc}")
            return 11

        status_by_code = {
            str(item.get("code") or "").strip().lower(): item
            for item in statuses
        }
        if not statuses:
            print("Wallet returned no payment methods for these fare terms.")

        for code, item in status_by_code.items():
            print(
                f"{code}: status={item.get('status')} | "
                f"message={item.get('status_message') or '(none)'}"
            )

        print("\n========== CASH DECISION ==========")
        cash_config = by_code.get("cash")
        cash_status = status_by_code.get("cash")
        if cash_config is None:
            print("CASH: BLOCKED — there is no 'cash' row in payment_method_configs.")
        elif cash_status and cash_status.get("status") == "ready":
            print("CASH: READY — Wallet certification returned cash as ready for this fare.")
            print("The native app should display Cash as a selectable method from this response.")
        elif cash_status:
            print(f"CASH: NOT READY — Wallet returned status={cash_status.get('status')}.")
            print(f"Reason: {cash_status.get('status_message') or '(no explanation returned)'}")
        else:
            print("CASH: NOT OFFERED — review the cash CONFIG GATE above.")
            print("An existing row is not automatically repaired by initialize_defaults(); it only inserts missing rows.")

        print("\n========== WALLET DECISION ==========")
        wallet_status = status_by_code.get("wallet")
        if wallet_status:
            print(f"WALLET: status={wallet_status.get('status')}")
            print(f"Reason: {wallet_status.get('status_message') or '(none)'}")
        else:
            wallet_config = by_code.get("wallet")
            if wallet_config is None:
                print("WALLET: No wallet configuration row exists.")
            else:
                print("WALLET: Not offered; review its CONFIG GATE above.")

        ready = [str(x.get("code")) for x in statuses if x.get("status") == "ready"]
        print("\n========== SUMMARY ==========")
        print(f"READY METHODS: {', '.join(ready) if ready else 'NONE'}")
        if "cash" not in ready:
            print("NEXT ACTION: Correct the Cash row/configuration in the Owner Payment Methods page.")
            print("Do not enable external gateways unless their Wallet collection/settlement lifecycle is implemented and tested.")
        else:
            print("NEXT ACTION: Cash is configured as ready. If the APK still hides it, inspect the exact API response and installed app build/OTA revision.")
        print("\nREAD-ONLY DIAGNOSTIC COMPLETE. No payment configuration or financial records were changed.")
        db.session.rollback()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
