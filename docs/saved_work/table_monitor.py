#!/usr/bin/env python3
"""
TABLE MONITOR - Watches for new tables and logs changes
Run this periodically to detect schema changes
"""

import sys
import json
import hashlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/app')

from app import create_app
from app.extensions import db
from sqlalchemy import inspect, text

class TableMonitor:
    """Monitors database schema for changes"""
    
    def __init__(self, state_file='/app/.table_state.json'):
        self.app = create_app()
        self.state_file = state_file
        self.previous_state = self.load_state()
    
    def load_state(self):
        """Load previous table state"""
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except:
            return {'tables': [], 'hash': '', 'last_check': None}
    
    def save_state(self, state):
        """Save current table state"""
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def get_current_state(self):
        """Get current database state"""
        with self.app.app_context():
            inspector = inspect(db.engine)
            tables = sorted(inspector.get_table_names())
            
            # Create a hash of the schema
            schema_hash = hashlib.md5(str(tables).encode()).hexdigest()
            
            return {
                'tables': tables,
                'hash': schema_hash,
                'last_check': datetime.now().isoformat(),
                'count': len(tables)
            }
    
    def check_for_changes(self):
        """Check for new or removed tables"""
        current = self.get_current_state()
        
        if not self.previous_state['tables']:
            print("📊 First run - establishing baseline")
            self.save_state(current)
            return current
        
        if current['hash'] != self.previous_state['hash']:
            print("\n" + "=" * 70)
            print("🔔 DATABASE SCHEMA CHANGE DETECTED!")
            print("=" * 70)
            print(f"Previous: {self.previous_state['count']} tables")
            print(f"Current:  {current['count']} tables")
            
            # Find new tables
            new_tables = set(current['tables']) - set(self.previous_state['tables'])
            if new_tables:
                print(f"\n✨ NEW TABLES FOUND: {len(new_tables)}")
                for table in sorted(new_tables):
                    print(f"   + {table}")
            
            # Find removed tables
            removed_tables = set(self.previous_state['tables']) - set(current['tables'])
            if removed_tables:
                print(f"\n🗑️  REMOVED TABLES: {len(removed_tables)}")
                for table in sorted(removed_tables):
                    print(f"   - {table}")
            
            print("\n" + "=" * 70)
            
            # Save new state
            self.save_state(current)
            return current
        else:
            print(f"✅ No schema changes detected (still {current['count']} tables)")
            return current
    
    def get_registered_tables_report(self):
        """Generate a report of all registered tables for developers"""
        with self.app.app_context():
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            print("\n" + "=" * 70)
            print("📋 REGISTERED DATABASE TABLES")
            print("=" * 70)
            print(f"Total: {len(tables)} tables\n")
            
            # Group by module
            modules = {
                'Core': [],
                'Auth': [],
                'Wallet': [],
                'Transport': [],
                'Accommodation': [],
                'Events': [],
                'Admin': [],
                'Other': []
            }
            
            for table in tables:
                if table.startswith('user') or table in ['users', 'roles', 'permissions']:
                    modules['Auth'].append(table)
                elif table in ['transactions', 'wallet', 'agent_commissions', 'payout_requests', 'ledger_entries', 'fx_rates']:
                    modules['Wallet'].append(table)
                elif 'transport' in table:
                    modules['Transport'].append(table)
                elif 'accommodation' in table:
                    modules['Accommodation'].append(table)
                elif 'event' in table:
                    modules['Events'].append(table)
                elif table in ['organisations', 'organisation_members', 'compliance_cases']:
                    modules['Admin'].append(table)
                elif table in ['alembic_version']:
                    pass  # Skip
                else:
                    modules['Other'].append(table)
            
            for module, tables_list in modules.items():
                if tables_list:
                    print(f"\n📁 {module} ({len(tables_list)} tables):")
                    for table in sorted(tables_list):
                        print(f"   - {table}")
            
            return modules

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Database Table Monitor')
    parser.add_argument('--check', action='store_true', help='Check for schema changes')
    parser.add_argument('--report', action='store_true', help='Generate registered tables report')
    parser.add_argument('--init', action='store_true', help='Initialize state file')
    
    args = parser.parse_args()
    
    monitor = TableMonitor()
    
    if args.init:
        current = monitor.get_current_state()
        monitor.save_state(current)
        print(f"✅ State initialized with {current['count']} tables")
    
    if args.check:
        monitor.check_for_changes()
    
    if args.report or (not args.check and not args.init and not args.report):
        monitor.get_registered_tables_report()

if __name__ == "__main__":
    main()
