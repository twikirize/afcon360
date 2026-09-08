# scripts/seed_accommodation_catalogs.py
"""
Seed / upsert the accommodation catalog lookup tables.

Run after the migration that creates the tables:
    flask db upgrade
    python scripts/seed_accommodation_catalogs.py

Idempotent: safe to re-run; updates existing rows' labels/flags if they differ.
"""

import sys, os
sys.path.insert(0, os.getcwd())

from app import create_app
from app.extensions import db
from app.accommodation.catalog_data import (
    PROPERTY_TYPE_CATALOG,
    LISTING_TYPE_LABELS,
    CANCELLATION_POLICY_TIERS,
    CANCELLATION_POLICY_TYPES,
    CANCELLATION_PHASES,
    NO_SHOW_CHARGE_TYPES,
    BOOKING_MODES,
    CURRENCIES,
)
from app.accommodation.models.catalog import (
    AccommodationPropertyTypeConfig,
    AccommodationListingTypeConfig,
    AccommodationPolicyTier,
    AccommodationBookingMode,
    AccommodationCurrency,
    PropertyTypeHostType,
    PropertyTypeListingType,
    AccommodationCancellationPolicyTypeConfig,
    AccommodationCancellationPhaseConfig,
    AccommodationNoShowChargeTypeConfig,
)


def _upsert(model, code_col, code, **fields):
    """Upsert a row by unique code column."""
    row = db.session.query(model).filter(code_col == code).first()
    if row:
        changed = False
        for k, v in fields.items():
            if getattr(row, k) != v:
                setattr(row, k, v)
                changed = True
        if changed:
            db.session.add(row)
        return row
    row = model(code=code, **fields)
    db.session.add(row)
    return row


def _upsert_junction(model, col1, col2, val1, val2, **fields):
    """Upsert a junction row by composite unique (col1, col2)."""
    row = db.session.query(model).filter(
        getattr(model, col1) == val1,
        getattr(model, col2) == val2,
    ).first()
    if row:
        changed = False
        for k, v in fields.items():
            if getattr(row, k) != v:
                setattr(row, k, v)
                changed = True
        if changed:
            db.session.add(row)
        return row
    row = model(**{col1: val1, col2: val2, **fields})
    db.session.add(row)
    return row


def main():
    app = create_app()
    with app.app_context():
        # ---- listing types FIRST (referenced by property type junctions) ----
        for sort_order, (code, label) in enumerate(LISTING_TYPE_LABELS.items()):
            _upsert(
                AccommodationListingTypeConfig,
                AccommodationListingTypeConfig.code,
                code,
                label=label,
                sort_order=sort_order,
                is_active=True,
            )

        # ---- property types ----
        for sort_order, (code, meta) in enumerate(PROPERTY_TYPE_CATALOG.items()):
            row = _upsert(
                AccommodationPropertyTypeConfig,
                AccommodationPropertyTypeConfig.code,
                code,
                label=meta["label"],
                commercial=meta["commercial"],
                sort_order=sort_order,
                is_active=True,
            )
            # host types
            for ht in meta["host_types"]:
                _upsert_junction(
                    PropertyTypeHostType,
                    "property_type_code",
                    "host_type",
                    code,
                    ht,
                    is_deleted=False,
                )
            # listing types
            for lt in meta["listing_types"]:
                _upsert_junction(
                    PropertyTypeListingType,
                    "property_type_code",
                    "listing_type_code",
                    code,
                    lt,
                    is_deleted=False,
                )

        # ---- cancellation policy tiers (simple) ----
        for sort_order, tier in enumerate(CANCELLATION_POLICY_TIERS):
            _upsert(
                AccommodationPolicyTier,
                AccommodationPolicyTier.code,
                tier["code"],
                label=tier["label"],
                description=tier["description"],
                icon=tier["icon"],
                sort_order=sort_order,
                is_active=True,
            )

        # ---- advanced cancellation policy types ----
        for sort_order, pt in enumerate(CANCELLATION_POLICY_TYPES):
            _upsert(
                AccommodationCancellationPolicyTypeConfig,
                AccommodationCancellationPolicyTypeConfig.code,
                pt["code"],
                label=pt["label"],
                description=pt["description"],
                pre_checkin_days=pt["pre_checkin_days"],
                pre_checkin_refund_pct=pt["pre_checkin_refund_pct"],
                mid_stay_refund_pct=pt["mid_stay_refund_pct"],
                no_show_penalty=pt["no_show_penalty"],
                sort_order=sort_order,
                is_active=True,
            )

        # ---- cancellation phases ----
        for sort_order, phase in enumerate(CANCELLATION_PHASES):
            _upsert(
                AccommodationCancellationPhaseConfig,
                AccommodationCancellationPhaseConfig.code,
                phase["code"],
                label=phase["label"],
                description=phase["description"],
                sort_order=sort_order,
                is_active=True,
            )

        # ---- no-show charge types ----
        for sort_order, ns in enumerate(NO_SHOW_CHARGE_TYPES):
            _upsert(
                AccommodationNoShowChargeTypeConfig,
                AccommodationNoShowChargeTypeConfig.code,
                ns["code"],
                label=ns["label"],
                description=ns["description"],
                sort_order=sort_order,
                is_active=True,
            )

        # ---- booking modes ----
        for sort_order, mode in enumerate(BOOKING_MODES):
            _upsert(
                AccommodationBookingMode,
                AccommodationBookingMode.code,
                mode["code"],
                label=mode["label"],
                is_default=mode["is_default"],
                sort_order=sort_order,
                is_active=True,
            )

        # ---- currencies ----
        for sort_order, cur in enumerate(CURRENCIES):
            _upsert(
                AccommodationCurrency,
                AccommodationCurrency.code,
                cur["code"],
                name=cur["name"],
                symbol=cur["symbol"],
                sort_order=sort_order,
                is_active=True,
            )

        db.session.commit()
        print("✅ Accommodation catalog tables seeded/updated.")


if __name__ == "__main__":
    main()