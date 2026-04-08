"""
Hardened Database Integrity Audit Script
Checks for missing timestamps, FK inconsistencies, and indexing gaps.
Refined to handle Dual-ID architecture (UUID vs BIGINT).
"""

import os
import sys
from sqlalchemy import inspect
from flask import Flask

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config import Config
from app.extensions import db

def create_minimal_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    db.init_app(app)
    return app

def audit_database():
    app = create_minimal_app()
    with app.app_context():
        inspector = inspect(db.engine)
        audit_results = {
            'missing_timestamps': [],
            'missing_fk_indexes': [],
            'id_type_mismatches': []
        }

        # Columns that are INTENTIONALLY strings (UUIDs, hashes, tokens)
        EXTERNAL_IDENTIFIERS = [
            'user_id', 'org_id', 'public_id', 'tenant_id', 'session_id',
            'request_id', 'correlation_id', 'key_id', 'tx_id', 'tx_hash',
            'device_id', 'tracking_device_id', 'client_request_id',
            'external_booking_id', 'gateway_transaction_id', 'provider_id',
            'resource_id', 'entity_id', 'context_id', 'correlation_id',
            'tax_id', 'group_booking_id'
        ]

        print("\n🔍 --- Starting Hardened AFCON 360 Database Audit ---")

        for table_name in inspector.get_table_names():
            # Skip system tables
            if table_name in ['alembic_version', 'spatial_ref_sys']:
                continue

            columns = inspector.get_columns(table_name)
            column_names = [col['name'] for col in columns]

            # 1. Check for missing created_at / updated_at
            missing_ts = []
            for col in ['created_at', 'updated_at']:
                if col not in column_names:
                    missing_ts.append(col)
            if missing_ts:
                audit_results['missing_timestamps'].append({'table': table_name, 'missing': missing_ts})

            # 2. Check for FKs without indexes
            foreign_keys = inspector.get_foreign_keys(table_name)
            for fk in foreign_keys:
                fk_col = fk['constrained_columns'][0]
                has_index = False
                for index in inspector.get_indexes(table_name):
                    if fk_col in index['column_names']:
                        has_index = True
                        break
                if not has_index:
                    audit_results['missing_fk_indexes'].append({
                        'table': table_name,
                        'column': fk_col,
                        'references': f"{fk['referred_table']}.{fk['referred_columns'][0]}"
                    })

            # 3. Check for ID type mismatches
            for col in columns:
                col_name = col['name']
                col_type = str(col['type']).upper()

                # PK 'id' MUST be BIGINT
                if col_name == 'id' and 'BIGINT' not in col_type:
                    audit_results['id_type_mismatches'].append({
                        'table': table_name,
                        'column': col_name,
                        'current_type': col_type,
                        'expected': 'BIGINT'
                    })

                # Check for hidden BIGINT FKs that are still INTEGER
                # We only flag if it's NOT in our list of intentional external strings
                if col_name.endswith('_id') and col_name not in EXTERNAL_IDENTIFIERS:
                    if 'INT' in col_type and 'BIGINT' not in col_type:
                        audit_results['id_type_mismatches'].append({
                            'table': table_name,
                            'column': col_name,
                            'current_type': col_type,
                            'expected': 'BIGINT (Internal FK)'
                        })

        # --- Report Results ---
        print("\n📊 --- Audit Results Summary ---")

        if audit_results['missing_timestamps']:
            print("\n⚠️ TABLES MISSING TIMESTAMPS:")
            for res in audit_results['missing_timestamps']:
                print(f"  - {res['table']}: missing {res['missing']}")
        else:
            print("\n✅ All tables have timestamps.")

        if audit_results['id_type_mismatches']:
            print("\n❌ ID TYPE MISMATCHES (Critical):")
            for res in audit_results['id_type_mismatches']:
                print(f"  - {res['table']}.{res['column']}: is {res['current_type']}, should be {res['expected']}")
        else:
            print("✅ No ID type mismatches found.")

        if audit_results['missing_fk_indexes']:
            print("\n⚡ MISSING FOREIGN KEY INDEXES (Performance):")
            for res in audit_results['missing_fk_indexes']:
                print(f"  - {res['table']}.{res['column']} -> {res['references']}")
        else:
            print("✅ All foreign keys are indexed.")

        if not any(audit_results.values()):
            print("\n💎 DATABASE IS PERFECTLY HARDENED.")

        print("\n🏁 --- Audit Complete ---")

if __name__ == '__main__':
    audit_database()
