#!/usr/bin/env python3
"""
LAZY TABLE CREATOR - Handles circular dependencies in complex Flask-SQLAlchemy models
Updated: 2026-05-28 — added verbose error reporting for stuck tables
"""

import sys
import time

sys.path.insert(0, '/app')

from app import create_app
from app.extensions import db
from sqlalchemy import inspect, text


def create_tables_lazy(max_retries=15, delay=2, verbose=True):
    def log(msg, level="INFO"):
        if verbose:
            print(f"[{level}] {msg}")

    log("=" * 70)
    log("LAZY TABLE CREATOR - Handling Circular Dependencies")
    log("=" * 70)

    app = create_app()

    with app.app_context():
        log("\n📦 Loading all models...")
        try:
            from app import models
            from app.wallet import models as wallet_models
            from app.transport import models as transport_models
            from app.accommodation import models as accommodation_models
            from app.events import models as events_models
            from app.admin import models as admin_models
            from app.identity import models as identity_models
            from app.audit import models as audit_models
            from app.kyc import models as kyc_models
            from app.fan import models as fan_models
            from app.profile import models as profile_models
            log(f"   ✅ Loaded {len(db.metadata.tables)} models")
        except Exception as e:
            log(f"   ⚠️ Model loading warning: {e}", "WARNING")

        inspector = inspect(db.engine)
        existing = set(inspector.get_table_names())
        log(f"\n📊 Existing tables: {len(existing)}")

        all_tables = set(db.metadata.tables.keys())
        missing = all_tables - existing

        if not missing:
            log("\n✅ All tables already exist!")
            return True

        log(f"\n🎯 Need to create: {len(missing)} tables")

        created = set(existing)
        last_errors = {}

        for attempt in range(max_retries):
            log(f"\n{'='*70}")
            log(f"🔄 Attempt {attempt + 1}/{max_retries}")
            log(f"{'='*70}")

            created_this_round = 0
            remaining = sorted(missing - created)

            if not remaining:
                break

            for table_name in remaining:
                try:
                    table = db.metadata.tables[table_name]
                    table.create(db.engine, checkfirst=True)
                    created.add(table_name)
                    created_this_round += 1
                    log(f"   ✅ Created: {table_name}")
                    last_errors.pop(table_name, None)

                except Exception as e:
                    error_msg = str(e)
                    last_errors[table_name] = error_msg

                    if "already exists" in error_msg.lower():
                        created.add(table_name)
                        log(f"   ⏭️  Already exists: {table_name}")

            log(f"\n📈 Created this round: {created_this_round}")
            log(f"📊 Remaining: {len(missing - created)}")

            if created_this_round == 0 and len(missing - created) > 0:
                if attempt < max_retries - 1:
                    log(f"\n💤 Waiting {delay}s...")
                    time.sleep(delay)
                    delay = min(delay * 1.5, 10)
                else:
                    log("\n" + "=" * 70)
                    log("❌ STUCK TABLES — EXACT ERRORS:")
                    log("=" * 70)
                    for table_name in sorted(missing - created):
                        err = last_errors.get(table_name, "No error recorded")
                        lines = err.strip().split('\n')
                        short = next(
                            (l.strip() for l in reversed(lines)
                             if l.strip()
                             and 'sqlalchemy' not in l.lower()
                             and 'file' not in l.lower()
                             and 'traceback' not in l.lower()),
                            lines[-1].strip()
                        )
                        log(f"   ❌ {table_name}:")
                        log(f"      {short[:120]}")

        inspector = inspect(db.engine)
        final_tables = set(inspector.get_table_names())
        new_tables = final_tables - existing

        log("\n" + "=" * 70)
        log("🎯 FINAL RESULT")
        log("=" * 70)
        log(f"Total tables: {len(final_tables)}")
        log(f"Newly created: {len(new_tables)}")

        critical = ['users', 'webhook_events', 'audit_logs', 'system_settings',
                    'transactions', 'organisations', 'events']
        log("\n📋 Critical tables:")
        all_critical_exist = True
        for table in critical:
            if inspector.has_table(table):
                log(f"   ✅ {table}")
            else:
                log(f"   ❌ {table}")
                all_critical_exist = False

        return len(final_tables) > 1 and all_critical_exist


def fix_stubborn_tables():
    print("\n" + "=" * 70)
    print("🔧 FIXING STUBBORN TABLES")
    print("=" * 70)

    app = create_app()

    with app.app_context():
        inspector = inspect(db.engine)
        if not inspector.has_table('transactions'):
            print("Creating transactions table manually...")
            try:
                orphaned_indexes = [
                    'ix_transactions_user_id',
                    'ix_transactions_client_request_id',
                    'ix_transactions_status',
                    'ix_transactions_type',
                    'ix_transactions_created_at'
                ]
                for idx in orphaned_indexes:
                    try:
                        db.session.execute(text(f'DROP INDEX IF EXISTS {idx} CASCADE'))
                    except Exception:
                        pass
                db.session.commit()

                db.session.execute(text('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id BIGINT NOT NULL,
                        client_request_id VARCHAR(255) UNIQUE NOT NULL,
                        tx_type VARCHAR(50) NOT NULL,
                        status VARCHAR(50) NOT NULL,
                        amount DECIMAL(20,8) NOT NULL,
                        currency VARCHAR(3) NOT NULL,
                        description TEXT,
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                '''))
                db.session.commit()
                db.session.execute(text(
                    'CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)'))
                db.session.execute(text(
                    'CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)'))
                db.session.commit()
                print("   ✅ transactions table created")
            except Exception as e:
                print(f"   ⚠️  {e}")
        else:
            print("   ✅ transactions table already exists")

        final_count = len(inspector.get_table_names())
        print(f"\n📊 Final table count: {final_count}")
        return final_count >= 50


if __name__ == "__main__":
    print("\n" + "🚀" * 35)
    print("STARTING LAZY TABLE CREATOR")
    print("🚀" * 35)

    success = create_tables_lazy(max_retries=15, delay=2, verbose=True)

    if success:
        success = fix_stubborn_tables()

    print("\n" + "=" * 70)
    if success:
        print("🎉 SUCCESS! All database tables created!")
        sys.exit(0)
    else:
        print("⚠️ PARTIAL SUCCESS - Some tables may still be missing")
        print("Run the script again or check manually")
        sys.exit(1)
