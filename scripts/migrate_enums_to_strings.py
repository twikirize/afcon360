#!/usr/bin/env python3
"""
Legacy/Deferred ENUM-to-String Migration Helper (Deferred — not for current AFCON360 work)

This script generates candidate SQL for an ENUM-to-String conversion using the
expand-contract pattern. It is **not** part of the active AFCON360 plan.

- No enum-to-string or string-to-enum conversion is currently authorized.
- Existing database representations must be preserved (ENUMs stay enums, strings stay strings).
- The script only generates candidate SQL; it does not apply changes.
- The `--execute` option is not implemented and exits with a non‑zero status.
- Reuse requires a new, explicitly approved future scope.

Usage:
    python scripts/migrate_enums_to_strings.py --dry-run    # Preview generated SQL
    python scripts/migrate_enums_to_strings.py --execute    # Not implemented (exits non‑zero)

The migration follows the expand-contract pattern (historical reference):
    PHASE 1 (EXPAND): Add new String columns alongside existing ENUM columns
    PHASE 2 (MIGRATE): Backfill data from ENUM columns to String columns
    PHASE 3 (SWITCH): Add CHECK constraints, update application code
    PHASE 4 (CONTRACT): Drop old ENUM columns and types
"""

import argparse
import sys
from typing import List, Dict, Any

# All enum columns to migrate - discovered from codebase
ENUM_COLUMNS = [
    # Audit module
    {"table": "financial_audit_logs", "column": "transaction_type", "enum_type": "audittransactiontype", "values": ["deposit", "withdrawal", "transfer", "refund", "fee", "reversal", "currency_exchange", "commission", "payout", "exchange"]},
    {"table": "api_audit_logs", "column": "status", "enum_type": "apicallstatus", "values": ["success", "failure", "timeout", "rate_limited"]},
    {"table": "data_access_logs", "column": "access_type", "enum_type": "dataaccesstype", "values": ["read", "export", "delete", "modify"]},
    {"table": "security_event_logs", "column": "severity", "enum_type": "auditseverity", "values": ["info", "warning", "critical", "security"]},
    
    # Profile module
    {"table": "user_profiles", "column": "gender", "enum_type": "gender_enum", "values": ["male", "female", "other", "unspecified"]},
    {"table": "user_profiles", "column": "id_type", "enum_type": "id_type_enum", "values": ["passport", "national_id", "driver_license", "other"]},
    {"table": "user_profiles", "column": "verification_status", "enum_type": "verification_status_enum", "values": ["pending", "verified", "rejected", "suspended"]},
    {"table": "user_profiles", "column": "kyc_level", "enum_type": "kyc_level_enum", "values": ["basic", "enhanced", "government"]},
    
    # Identity module
    {"table": "organisations", "column": "verification_status", "enum_type": "org_verification_status", "values": ["unverified", "pending", "verified", "rejected", "suspended", "expired"]},
    {"table": "organisations", "column": "lifecycle_state", "enum_type": "org_lifecycle_state", "values": ["draft", "registered", "approved", "suspended", "closed"]},
    {"table": "organisations", "column": "business_category", "enum_type": "org_business_category", "values": []},  # Uses OrganizationType enum
    
    {"table": "organisation_verifications", "column": "status", "enum_type": "org_verification_status", "values": ["unverified", "pending", "verified", "rejected", "suspended", "expired"]},
    {"table": "organisation_kyb_checks", "column": "check_type", "enum_type": "org_kyb_check_type", "values": ["identity", "tax", "license", "ubo", "sanctions"]},
    {"table": "organisation_kyb_checks", "column": "status", "enum_type": "org_kyb_check_status", "values": ["pending", "passed", "failed", "manual_review"]},
    {"table": "organisation_ubos", "column": "ubo_type", "enum_type": "ubo_type", "values": ["individual", "corporate"]},
    {"table": "organisation_kyb_documents", "column": "verification_status", "enum_type": "kyb_doc_status", "values": ["pending", "verified", "rejected"]},
    {"table": "individual_verifications", "column": "status", "enum_type": "ind_verification_status", "values": ["pending", "verified", "rejected", "expired", "suspended"]},
    {"table": "individual_documents", "column": "document_type", "enum_type": "ind_document_type", "values": ["id_card", "passport", "driver_license", "proof_of_address"]},
    {"table": "organisation_licenses", "column": "verification_status", "enum_type": "doc_verification_status", "values": ["pending", "verified", "rejected"]},
    {"table": "organisation_audit_logs", "column": "change_type", "enum_type": "org_change_type", "values": ["create", "update", "delete", "verify", "suspend"]},
    {"table": "organisation_audit_logs", "column": "source", "enum_type": "org_change_source", "values": ["system", "user", "admin"]},
    {"table": "organisation_documents", "column": "verification_status", "enum_type": "doc_verification_status", "values": ["pending", "verified", "rejected"]},
    {"table": "compliance_audit_logs", "column": "entity_type", "enum_type": "entity_type", "values": ["organisation", "individual"]},
    {"table": "compliance_audit_logs", "column": "decision", "enum_type": "compliance_decision", "values": ["allowed", "blocked", "conditional"]},
    {"table": "compliance_audit_logs", "column": "risk_tier", "enum_type": "risk_tier", "values": ["low", "medium", "high"]},
    {"table": "compliance_settings", "column": "enforcement_level", "enum_type": "compliance_enforcement_level", "values": ["optional", "conditional", "mandatory"]},
    {"table": "organisation_payment_gateways", "column": "provider", "enum_type": "payment_gateway_provider", "values": ["flutterwave", "paystack", "mtn_momo", "airtel_money", "visa", "mastercard", "paypal", "alipay", "wechat_pay", "bank_transfer", "stripe", "mpesa"]},
    {"table": "organisation_payment_gateways", "column": "environment", "enum_type": "gateway_environment", "values": ["sandbox", "production"]},
    
    # Wallet module
    {"table": "transactions", "column": "tx_type", "enum_type": "transaction_type_enum", "values": ["deposit", "withdraw", "transfer", "fee", "refund", "adjustment"]},
    {"table": "transactions", "column": "status", "enum_type": "transaction_status_enum", "values": ["pending", "completed", "failed", "cancelled"]},
    {"table": "regulatory_volume_policies", "column": "daily_window_mode", "enum_type": "window_mode_enum", "values": ["calendar", "rolling"]},
    {"table": "regulatory_volume_policies", "column": "monthly_window_mode", "enum_type": "window_mode_enum", "values": ["calendar", "rolling"]},
    {"table": "regulatory_volume_policy_changes", "column": "proposed_daily_mode", "enum_type": "window_mode_enum", "values": ["calendar", "rolling"]},
    {"table": "regulatory_volume_policy_changes", "column": "proposed_monthly_mode", "enum_type": "window_mode_enum", "values": ["calendar", "rolling"]},
    {"table": "regulatory_volume_policy_changes", "column": "status", "enum_type": "rvpcr_status_enum", "values": ["pending", "approved", "rejected", "cancelled", "expired"]},
    
    # Transport module
    {"table": "transport_ride_requests", "column": "service_type", "enum_type": "servicetype", "values": ["airport_arrival", "airport_departure", "stadium_shuttle", "hotel_transfer", "city_tour", "on_demand", "scheduled_route", "custom_tour"]},
    {"table": "transport_vehicles", "column": "vehicle_class", "enum_type": "vehicleclass", "values": ["economy", "comfort", "premium", "luxury", "van", "bus"]},
    {"table": "transport_offerings", "column": "provider_type", "enum_type": "providertype", "values": ["individual_driver", "hotel_fleet", "tour_operator", "transport_company", "external_platform"]},
    {"table": "transport_offerings", "column": "service_type", "enum_type": "servicetype", "values": ["airport_arrival", "airport_departure", "stadium_shuttle", "hotel_transfer", "city_tour", "on_demand", "scheduled_route", "custom_tour"]},
    {"table": "transport_offerings", "column": "currency", "enum_type": "currency", "values": ["USD", "EUR", "GBP", "XOF", "XAF", "NGN", "KES", "GHS", "ZAR", "UGX"]},
    {"table": "transport_offerings", "column": "payment_status", "enum_type": "paymentstatus", "values": ["pending", "authorized", "captured", "partially_captured", "refunded", "partially_refunded", "failed", "cancelled"]},
    {"table": "transport_bookings", "column": "service_type", "enum_type": "servicetype", "values": ["airport_arrival", "airport_departure", "stadium_shuttle", "hotel_transfer", "city_tour", "on_demand", "scheduled_route", "custom_tour"]},
    {"table": "transport_bookings", "column": "currency", "enum_type": "currency", "values": ["USD", "EUR", "GBP", "XOF", "XAF", "NGN", "KES", "GHS", "ZAR", "UGX"]},
    {"table": "transport_bookings", "column": "payment_status", "enum_type": "paymentstatus", "values": ["pending", "authorized", "captured", "partially_captured", "refunded", "partially_refunded", "failed", "cancelled"]},
    {"table": "transport_incidents", "column": "severity", "enum_type": "incidentseverity", "values": ["info", "low", "medium", "high", "critical"]},
    {"table": "vehicle_marketplace_listings", "column": "listing_status", "enum_type": "marketplacelistingstatus", "values": ["draft", "active", "paused", "filled", "expired", "closed"]},
    {"table": "driver_vehicle_applications", "column": "status", "enum_type": "applicationstatus", "values": ["pending", "under_review", "approved", "rejected", "withdrawn", "expired"]},
    {"table": "vehicle_contracts", "column": "compensation_model", "enum_type": "compensationmodel", "values": ["fixed_fee", "percentage", "per_km", "per_hour", "daily_rate", "weekly_rate", "monthly_rate", "revenue_share"]},
    {"table": "vehicle_contracts", "column": "status", "enum_type": "contractstatus", "values": ["draft", "active", "suspended", "terminated", "expired", "pending_signature"]},
    
    # Admin compliance
    {"table": "compliance_cases", "column": "case_type", "enum_type": "compliancecasetype", "values": ["kyc_review", "kyb_review", "aml_alert", "payout_review", "data_request", "flag_escalation", "license_review", "other"]},
    {"table": "compliance_cases", "column": "status", "enum_type": "compliancecasestatus", "values": ["open", "in_review", "pending_info", "approved", "rejected", "escalated", "closed"]},
    {"table": "compliance_cases", "column": "priority", "enum_type": "compliancecasepriority", "values": ["critical", "high", "medium", "low"]},
    {"table": "data_subject_requests", "column": "request_type", "enum_type": "datasubjectrequesttype", "values": ["access", "deletion", "rectification", "portability", "objection"]},
    {"table": "data_subject_requests", "column": "status", "enum_type": "datasubjectrequeststatus", "values": ["pending", "verified", "processing", "completed", "rejected", "expired"]},
    {"table": "compliance_reports", "column": "report_type", "enum_type": "compliancereporttype", "values": ["kyc_summary", "aml_summary", "payout_summary", "case_history", "audit_trail", "risk_assessment", "regulatory_filing"]},
    
    # Accommodation
    {"table": "accommodation_properties", "column": "property_type", "enum_type": "accommodationpropertytype", "values": ["hotel", "apartment", "villa", "hostel", "guesthouse"]},
    {"table": "accommodation_properties", "column": "listing_type", "enum_type": "accommodationlistingtype", "values": ["entire_place", "private_room", "shared_room"]},
    {"table": "accommodation_properties", "column": "cancellation_policy", "enum_type": "accommodationcancellationpolicy", "values": ["flexible", "moderate", "strict", "non_refundable"]},
    {"table": "accommodation_properties", "column": "status", "enum_type": "accommodationpropertystatus", "values": ["draft", "pending", "approved", "rejected", "suspended"]},
    {"table": "accommodation_properties", "column": "verification_status", "enum_type": "accommodationverificationstatus", "values": ["unverified", "pending", "verified", "rejected"]},
    {"table": "accommodation_bookings", "column": "status", "enum_type": "accommodationbookingstatus", "values": ["draft", "pending", "confirmed", "checked_in", "checked_out", "cancelled"]},
    {"table": "accommodation_bookings", "column": "payment_status", "enum_type": "accommodationpaymentstatus", "values": ["pending", "processing", "completed", "failed", "refunded"]},
    {"table": "accommodation_bookings", "column": "payment_method", "enum_type": "accommodationpaymentmethod", "values": ["card", "wallet", "bank_transfer", "cash", "mobile_money"]},
    {"table": "accommodation_reviews", "column": "status", "enum_type": "accommodationreviewstatus", "values": ["pending", "approved", "rejected", "flagged"]},
    {"table": "accommodation_property_documents", "column": "document_type", "enum_type": "propertydocumenttype", "values": ["id_document", "business_license", "tax_certificate", "property_deed", "insurance_certificate", "other"]},
    {"table": "accommodation_property_documents", "column": "status", "enum_type": "propertydocumentstatus", "values": ["pending", "approved", "rejected", "expired"]},
    {"table": "accommodation_availability_rules", "column": "reason", "enum_type": "accommodationblockedreason", "values": ["maintenance", "blocked", "seasonal", "owner_use"]},
]


def generate_expand_phase(enum_cols: List[Dict]) -> List[str]:
    """Generate SQL for Phase 1: Add new String columns alongside existing ENUM columns."""
    statements = []
    statements.append("-- ============================================================================")
    statements.append("-- PHASE 1: EXPAND - Add new String columns alongside existing ENUM columns")
    statements.append("-- ============================================================================")
    statements.append("")
    
    for col in enum_cols:
        table = col["table"]
        column = col["column"]
        new_column = f"{column}_new"
        max_len = max(len(v) for v in col["values"]) if col["values"] else 50
        max_len = max(max_len, 20)  # minimum 20 chars
        max_len = min(max_len, 100)  # cap at 100
        
        # Add new column
        stmt = f"ALTER TABLE {table} ADD COLUMN {new_column} VARCHAR({max_len});"
        statements.append(stmt)
    
    return statements


def generate_migrate_phase(enum_cols: List[Dict]) -> List[str]:
    """Generate SQL for Phase 2: Backfill data from ENUM columns to String columns."""
    statements = []
    statements.append("")
    statements.append("-- ============================================================================")
    statements.append("-- PHASE 2: MIGRATE - Backfill data from ENUM columns to String columns")
    statements.append("-- ============================================================================")
    statements.append("")
    
    for col in enum_cols:
        table = col["table"]
        column = col["column"]
        new_column = f"{column}_new"
        
        # Backfill data
        stmt = f"UPDATE {table} SET {new_column} = {column}::text WHERE {column} IS NOT NULL;"
        statements.append(stmt)
    
    return statements


def generate_switch_phase(enum_cols: List[Dict]) -> List[str]:
    """Generate SQL for Phase 3: Add CHECK constraints and switch application."""
    statements = []
    statements.append("")
    statements.append("-- ============================================================================")
    statements.append("-- PHASE 3: SWITCH - Add CHECK constraints and prepare for switch")
    statements.append("-- ============================================================================")
    statements.append("")
    
    for col in enum_cols:
        table = col["table"]
        column = col["column"]
        new_column = f"{column}_new"
        constraint_name = f"ck_{table}_{column}"
        
        if col["values"]:
            values_str = ", ".join(f"'{v}'" for v in col["values"])
            # Add CHECK constraint on new column
            stmt = f"ALTER TABLE {table} ADD CONSTRAINT {constraint_name} CHECK ({new_column} IN ({values_str}));"
            statements.append(stmt)
    
    statements.append("")
    statements.append("-- After this phase, update application code to use the _new columns")
    statements.append("-- Then rename columns: ALTER TABLE ... RENAME COLUMN old TO old_backup; RENAME new TO original;")
    
    return statements


def generate_contract_phase(enum_cols: List[Dict]) -> List[str]:
    """Generate SQL for Phase 4: Drop old ENUM columns and types."""
    statements = []
    statements.append("")
    statements.append("-- ============================================================================")
    statements.append("-- PHASE 4: CONTRACT - Drop old ENUM columns and types")
    statements.append("-- ============================================================================")
    statements.append("")
    statements.append("-- WARNING: Only run after application code has been switched to new columns!")
    statements.append("")
    
    for col in enum_cols:
        table = col["table"]
        column = col["column"]
        new_column = f"{column}_new"
        enum_type = col["enum_type"]
        
        # Drop old column
        statements.append(f"ALTER TABLE {table} DROP COLUMN {column};")
        # Rename new column to original name
        statements.append(f"ALTER TABLE {table} RENAME COLUMN {new_column} TO {column};")
        statements.append("")
    
    # Drop ENUM types (only after all columns using them are dropped)
    enum_types = set(col["enum_type"] for col in enum_cols if col["enum_type"])
    statements.append("-- Drop ENUM types (only after all columns using them are dropped)")
    for enum_type in sorted(enum_types):
        statements.append(f"DROP TYPE IF EXISTS {enum_type};")
    
    return statements


def generate_full_migration(dry_run: bool = True) -> str:
    """Generate the complete migration SQL."""
    output = []
    output.append("-- ============================================================================")
    output.append("-- PostgreSQL ENUM to String Migration - Expand-Contract Pattern")
    output.append("-- Generated by migrate_enums_to_strings.py")
    output.append("-- ============================================================================")
    output.append("")
    
    if dry_run:
        output.append("-- DRY RUN MODE - No changes will be made")
        output.append("")
    
    output.extend(generate_expand_phase(ENUM_COLUMNS))
    output.extend(generate_migrate_phase(ENUM_COLUMNS))
    output.extend(generate_switch_phase(ENUM_COLUMNS))
    output.extend(generate_contract_phase(ENUM_COLUMNS))
    
    output.append("")
    output.append("-- ============================================================================")
    output.append("-- Migration complete")
    output.append("-- ============================================================================")
    
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Generate ENUM to String migration SQL")
    parser.add_argument("--dry-run", action="store_true", help="Preview migration without executing")
    parser.add_argument("--execute", action="store_true", help="Not implemented — exits with error (use --dry-run)")
    parser.add_argument("--output", help="Output file for generated SQL")
    
    args = parser.parse_args()

    # Fail closed before generating or writing any candidate SQL. The option
    # exists only for backwards-compatible CLI recognition; this tool never
    # applies schema changes.
    if args.execute:
        parser.error(
            "--execute is intentionally unsupported; this script only generates candidate SQL"
        )

    # Default to dry-run when no mode is specified. There is no write/apply
    # mode in this utility; --output only writes a review artifact.
    if not args.dry_run:
        args.dry_run = True

    sql = generate_full_migration(dry_run=args.dry_run)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as output_file:
            output_file.write(sql)
        print(f"Migration SQL written to {args.output}")
    else:
        print(sql)

    print(f"\nTotal enum columns to migrate: {len(ENUM_COLUMNS)}")


if __name__ == "__main__":
    main()