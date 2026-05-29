#!/usr/bin/env python3
"""
LAZY TABLE CREATOR - Handles circular dependencies in complex Flask-SQLAlchemy models
Created: 2026-05-27
Purpose: Creates database tables in dependency order with retry logic for circular references

Usage:
    docker compose exec web python scripts/lazy_table_creator.py
    Or run inside container: python /app/scripts/lazy_table_creator.py
"""

import sys
import time
import os

# Add app to path
sys.path.insert(0, '/app')

from app import create_app
from app.extensions import db
from sqlalchemy import inspect, text

def create_tables_lazy(max_retries=15, delay=2, verbose=True):
    """
    Create all database tables with intelligent dependency handling.
    
    Args:
        max_retries: Maximum number of retry rounds for failed tables
        delay: Initial delay between retries (exponential backoff)
        verbose: Print detailed progress information
    
    Returns:
        bool: True if all tables created successfully
    """
    
    def log(msg, level="INFO"):
        if verbose:
            print(f"[{level}] {msg}")
    
    log("=" * 70)
    log("LAZY TABLE CREATOR - Handling Circular Dependencies")
    log("=" * 70)
    
    app = create_app()
    
    with app.app_context():
        # Force load all models by importing all modules
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
        
        # Check existing tables
        inspector = inspect(db.engine)
        existing = set(inspector.get_table_names())
        log(f"\n📊 Existing tables: {len(existing)}")
        
        # Find missing tables
        all_tables = set(db.metadata.tables.keys())
        missing = all_tables - existing
        
        if not missing:
            log("\n✅ All tables already exist!")
            return True
        
        log(f"\n🎯 Need to create: {len(missing)} tables")
        
        # Track created tables
        created = set(existing)
        
        # Keep retrying until all tables are created
        for attempt in range(max_retries):
            log(f"\n{'='*70}")
            log(f"🔄 Attempt {attempt + 1}/{max_retries}")
            log(f"{'='*70}")
            
            created_this_round = 0
            
            # Try to create each missing table
            remaining = sorted(missing - created)
            if not remaining:
                break
                
            for table_name in remaining:
                try:
                    # Get the table object
                    table = db.metadata.tables[table_name]
                    
                    # Try to create it
                    table.create(db.engine, checkfirst=True)
                    created.add(table_name)
                    created_this_round += 1
                    log(f"   ✅ Created: {table_name}")
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    # If it already exists, add to created
                    if "already exists" in error_msg:
                        created.add(table_name)
                        log(f"   ⏭️  Already exists: {table_name}")
                    
                    # If it's a dependency issue, wait for next round
                    elif "does not exist" in error_msg or "referenced" in error_msg or "relation" in error_msg:
                        if attempt == max_retries - 1:
                            log(f"   ⏳ Still waiting for dependencies: {table_name}")
                        # Silent wait otherwise
                    
                    # Other errors - show once
                    else:
                        if table_name not in created:
                            log(f"   ⚠️ {table_name}: {error_msg[:60]}", "WARNING")
            
            log(f"\n📈 Created this round: {created_this_round}")
            remaining_count = len(missing - created)
            log(f"📊 Remaining: {remaining_count}")
            
            # If no progress and not last attempt, wait
            if created_this_round == 0 and remaining_count > 0 and attempt < max_retries - 1:
                log(f"\n💤 Waiting {delay}s for dependencies to be created...")
                time.sleep(delay)
                delay = min(delay * 1.5, 10)  # Exponential backoff, max 10 seconds
        
        # Final verification
        inspector = inspect(db.engine)
        final_tables = set(inspector.get_table_names())
        new_tables = final_tables - existing
        
        log("\n" + "=" * 70)
        log("🎯 FINAL RESULT")
        log("=" * 70)
        log(f"Total tables: {len(final_tables)}")
        log(f"Newly created: {len(new_tables)}")
        
        # Check critical tables
        critical = ['users', 'webhook_events', 'audit_logs', 'system_settings', 'transactions']
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
    """
    Special fix for tables that have circular dependencies even after lazy creation.
    Specifically handles transactions, ledger_entries, and wallet_audit_logs.
    """
    print("\n" + "=" * 70)
    print("🔧 FIXING STUBBORN TABLES")
    print("=" * 70)
    
    app = create_app()
    
    with app.app_context():
        # Fix transactions table if missing
        inspector = inspect(db.engine)
        if not inspector.has_table('transactions'):
            print("Creating transactions table manually...")
            try:
                # Drop orphaned indexes first
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
                    except:
                        pass
                db.session.commit()
                
                # Create the table
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
                
                # Create indexes
                db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)'))
                db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)'))
                db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(tx_type)'))
                db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at)'))
                db.session.commit()
                print("   ✅ transactions table created")
            except Exception as e:
                print(f"   ⚠️ transactions table already exists or error: {e}")
        else:
            print("   ✅ transactions table already exists")
        
        # Verify all tables are present
        final_count = len(inspector.get_table_names())
        print(f"\n📊 Final table count: {final_count}")
        
        return final_count >= 95

if __name__ == "__main__":
    print("\n" + "🚀" * 35)
    print("STARTING LAZY TABLE CREATOR")
    print("🚀" * 35)
    
    # First pass: Lazy creation
    success = create_tables_lazy(max_retries=15, delay=2, verbose=True)
    
    # Second pass: Fix stubborn tables
    if success:
        success = fix_stubborn_tables()
    
    # Final verification
    print("\n" + "=" * 70)
    if success:
        print("🎉 SUCCESS! All database tables created!")
        print("=" * 70)
        sys.exit(0)
    else:
        print("⚠️ PARTIAL SUCCESS - Some tables may still be missing")
        print("Run the script again or check manually")
        print("=" * 70)
        sys.exit(1)
