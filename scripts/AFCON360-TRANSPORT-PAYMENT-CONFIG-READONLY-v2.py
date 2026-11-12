"""Read-only AFCON360 transport payment configuration inspection.

Important: all interactive prompts are collected BEFORE a database connection
is opened. This avoids holding an idle-in-transaction session while the user
enters the rider/fare details.

This script only SELECTs from payment_method_configs and PostgreSQL settings.
It does not modify records and deliberately does not print API keys/secrets or
config_json contents.
"""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def mask_identifier(value: str) -> str:
    value = value.strip()
    if "@" in value:
        local, _, domain = value.partition("@")
        return (local[:1] + "***@" + domain) if local else "***@" + domain
    if len(value) > 4:
        return "*" * (len(value) - 4) + value[-4:]
    return "*" * len(value)


def normalize_items(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, dict):
        # Configs may be represented as {"USD": true} or {"currencies": [...]}.
        if "currencies" in value and isinstance(value["currencies"], (list, tuple, set)):
            return {str(x).strip().upper() for x in value["currencies"] if str(x).strip()}
        if "timings" in value and isinstance(value["timings"], (list, tuple, set)):
            return {str(x).strip().lower() for x in value["timings"] if str(x).strip()}
        return {str(k).strip().upper() for k, enabled in value.items() if enabled}
    if isinstance(value, (list, tuple, set)):
        return {str(x).strip().upper() for x in value if str(x).strip()}
    text = str(value).strip()
    if not text:
        return set()
    try:
        decoded = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        decoded = None
    if decoded is not None and decoded is not value:
        return normalize_items(decoded)
    return {part.strip().upper() for part in text.replace(";", ",").split(",") if part.strip()}


def as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def main() -> int:
    print("AFCON360 TRANSPORT PAYMENT CONFIGURATION — READ ONLY")
    print("Collecting inputs before opening the database connection.\n")

    # Collect inputs first. No app context, ORM session, engine or DB connection yet.
    rider_ref = input("Rider test-account email or internal numeric user ID: ").strip()
    currency = input("Fare currency shown by the selected quote (e.g. UGX or USD): ").strip().upper()
    amount_raw = input("Exact fare amount shown for that quote: ").strip()
    try:
        fare_amount = Decimal(amount_raw)
        if fare_amount < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        print("ERROR: Enter a valid non-negative fare amount.", file=sys.stderr)
        return 2

    if not rider_ref or not currency:
        print("ERROR: Rider identifier and fare currency are required.", file=sys.stderr)
        return 2

    # Respect the already-selected phone-preview config; don't fall back to prod.
    os.environ.setdefault("APP_ENV", "phone-preview")
    os.environ.setdefault("FLASK_ENV", "development")

    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        from app.config import get_config
    except Exception as exc:
        print(f"ERROR: Could not import AFCON360 configuration/SQLAlchemy: {type(exc).__name__}: {exc}")
        return 3

    config = get_config()
    database_url = getattr(config, "SQLALCHEMY_DATABASE_URI", None)
    if not database_url:
        print("ERROR: Active AFCON360 configuration has no SQLALCHEMY_DATABASE_URI.")
        return 3

    parsed_url = make_url(database_url)
    print("\n========== FARE CONTEXT ==========")
    print(f"RIDER REFERENCE: {mask_identifier(rider_ref)}")
    print(f"FARE: {currency} {fare_amount}")
    print("REQUESTED TIMING: pay_on_completion")
    print(f"CONFIGURATION CLASS: {getattr(config, '__name__', type(config).__name__)}")
    print(f"CONFIGURED DATABASE: {parsed_url.database}")

    if parsed_url.database != "afcon360_test":
        print("STOP: This diagnostic is restricted to afcon360_test.", file=sys.stderr)
        return 4

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC", "connect_timeout": 10},
    )
    query = text("""
        SELECT
            method_id,
            display_name,
            method_type,
            provider_name,
            country_code,
            is_enabled,
            is_active,
            requires_phone,
            supported_currencies,
            allowed_timings,
            marketplace_collection_implemented,
            min_amount,
            max_amount,
            transaction_fee,
            last_test_result,
            is_deleted
        FROM payment_method_configs
        WHERE COALESCE(is_deleted, FALSE) = FALSE
        ORDER BY method_id
    """)

    try:
        # One short-lived connection. No prompts or user interaction inside this block.
        with engine.connect() as conn:
            db_name, db_role, timezone_name, idle_timeout = conn.execute(text("""
                SELECT current_database(), current_user,
                       current_setting('TimeZone'),
                       current_setting('idle_in_transaction_session_timeout')
            """)).one()
            print("\n========== DATABASE SAFETY ==========")
            print(f"CONNECTED DATABASE: {db_name}")
            print(f"DATABASE ROLE: {db_role}")
            print(f"SESSION TIMEZONE: {timezone_name}")
            print(f"IDLE-IN-TRANSACTION TIMEOUT: {idle_timeout}")
            if db_name != "afcon360_test" or timezone_name.upper() != "UTC":
                print("STOP: Database identity/timezone safety check failed.", file=sys.stderr)
                conn.rollback()
                return 5

            rows = conn.execute(query).mappings().all()
            # End the read transaction explicitly before formatting/reporting.
            conn.commit()

        print("\n========== PAYMENT METHOD CONFIGURATIONS ==========")
        if not rows:
            print("No non-deleted payment_method_configs rows were found.")
            return 0

        timing_needed = "PAY_ON_COMPLETION"
        for row in rows:
            method_id = row["method_id"]
            display_name = row["display_name"]
            method_type = row["method_type"]
            currencies = normalize_items(row["supported_currencies"])
            timings = normalize_items(row["allowed_timings"])
            enabled = bool(row["is_enabled"])
            active = bool(row["is_active"])
            collection_ready = bool(row["marketplace_collection_implemented"])
            min_amount = as_decimal(row["min_amount"])
            max_amount = as_decimal(row["max_amount"])
            currency_ok = currency in currencies if currencies else False
            timing_ok = timing_needed in timings
            amount_ok = (min_amount is None or fare_amount >= min_amount) and (max_amount is None or fare_amount <= max_amount)

            print("\n--- METHOD ---")
            print(f"METHOD ID: {method_id}")
            print(f"DISPLAY NAME: {display_name}")
            print(f"TYPE: {method_type}")
            print(f"PROVIDER: {row['provider_name']}")
            print(f"COUNTRY: {row['country_code']}")
            print(f"ENABLED: {enabled}")
            print(f"ACTIVE: {active}")
            print(f"REQUIRES PHONE: {bool(row['requires_phone'])}")
            print(f"SUPPORTED CURRENCIES: {sorted(currencies) if currencies else '(none / unrecognised format)'}")
            print(f"ALLOWED TIMINGS: {sorted(timings) if timings else '(none / unrecognised format)'}")
            print(f"MARKETPLACE COLLECTION IMPLEMENTED: {collection_ready}")
            print(f"MINIMUM AMOUNT: {min_amount if min_amount is not None else '(not set)'}")
            print(f"MAXIMUM AMOUNT: {max_amount if max_amount is not None else '(not set)'}")
            print(f"TRANSACTION FEE: {row['transaction_fee']}")
            print(f"LAST TEST RESULT: {row['last_test_result']}")
            print("CONFIG GATES FOR THIS FARE:")
            print(f"  enabled={enabled}; active={active}; collection={collection_ready}")
            print(f"  currency_match={currency_ok}; timing_match={timing_ok}; amount_in_range={amount_ok}")
            print("  CONFIG-ONLY RESULT:", "PASSES CONFIG GATES" if all((enabled, active, collection_ready, currency_ok, timing_ok, amount_ok)) else "NOT READY / NEEDS REVIEW")

        print("\n========== IMPORTANT LIMITATION ==========")
        print("This is a configuration-only inspection. It does not certify the rider's Wallet,")
        print("does not call the mobile payment-options endpoint, and does not prove the APK will")
        print("receive a method as ready. Rider eligibility must be checked separately through")
        print("the backend's authoritative payment-options service/endpoint.")
        print("No rows were inserted, updated or deleted. API keys and secrets were not selected or printed.")
        return 0
    except Exception as exc:
        try:
            engine.dispose()
        except Exception:
            pass
        print("\nREAD-ONLY DIAGNOSTIC FAILED:")
        print(f"{type(exc).__name__}: {exc}")
        print("No database changes were made.")
        return 6
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
