#!/usr/bin/env python3
"""
TABLE INSPECTOR & DOCUMENTATION GENERATOR
Automatically discovers, documents, and validates all database tables.
Run this to get a complete picture of your database schema.

Usage:
    docker compose exec web python scripts/table_inspector.py
    docker compose exec web python scripts/table_inspector.py --detail
    docker compose exec web python scripts/table_inspector.py --export
"""

import sys
import json
import time
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, '/app')

from app import create_app
from app.extensions import db
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError

class TableInspector:
    """Inspects and documents all database tables"""
    
    def __init__(self, verbose=True):
        self.app = create_app()
        self.verbose = verbose
        self.tables = {}
        
    def log(self, msg, level="INFO"):
        if self.verbose:
            print(f"[{level}] {msg}")
    
    def discover_all_tables(self):
        """Discover and analyze all tables in the database"""
        self.log("=" * 70)
        self.log("TABLE INSPECTOR - Database Discovery")
        self.log("=" * 70)
        
        with self.app.app_context():
            inspector = inspect(db.engine)
            
            # Get all tables
            table_names = inspector.get_table_names()
            self.log(f"\n📊 Found {len(table_names)} tables in database")
            
            # Analyze each table
            for table_name in sorted(table_names):
                self.log(f"\n📋 TABLE: {table_name}")
                
                # Get columns
                columns = inspector.get_columns(table_name)
                self.log(f"   Columns: {len(columns)}")
                for col in columns[:5]:  # Show first 5
                    self.log(f"     - {col['name']}: {col['type']}")
                if len(columns) > 5:
                    self.log(f"     ... and {len(columns)-5} more")
                
                # Get foreign keys
                fks = inspector.get_foreign_keys(table_name)
                if fks:
                    self.log(f"   Foreign Keys: {len(fks)}")
                    for fk in fks[:3]:
                        self.log(f"     - {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
                
                # Get indexes
                indexes = inspector.get_indexes(table_name)
                if indexes:
                    self.log(f"   Indexes: {len(indexes)}")
                
                # Store for later
                self.tables[table_name] = {
                    'columns': len(columns),
                    'foreign_keys': len(fks),
                    'indexes': len(indexes),
                    'sample_columns': [c['name'] for c in columns[:10]]
                }
            
            # Get total count
            result = db.session.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'"))
            total = result.scalar()
            
            self.log("\n" + "=" * 70)
            self.log("📊 SUMMARY")
            self.log("=" * 70)
            self.log(f"Total tables: {total}")
            self.log(f"Total columns: {sum(t['columns'] for t in self.tables.values())}")
            self.log(f"Total foreign keys: {sum(t['foreign_keys'] for t in self.tables.values())}")
            self.log(f"Total indexes: {sum(t['indexes'] for t in self.tables.values())}")
            
            return self.tables
    
    def check_critical_tables(self):
        """Verify critical tables exist"""
        critical = {
            'users': 'User authentication and management',
            'transactions': 'Wallet transactions',
            'webhook_events': 'Webhook processing',
            'audit_logs': 'System audit trail',
            'system_settings': 'System configuration',
            'agent_commissions': 'Commission tracking',
            'payout_requests': 'Payout management',
            'events': 'Event management',
            'wallet_audit_logs': 'Wallet audit trail',
            'ledger_entries': 'Financial ledger'
        }
        
        self.log("\n" + "=" * 70)
        self.log("🎯 CRITICAL TABLES CHECK")
        self.log("=" * 70)
        
        with self.app.app_context():
            inspector = inspect(db.engine)
            existing = set(inspector.get_table_names())
            
            all_present = True
            for table, purpose in critical.items():
                if table in existing:
                    self.log(f"   ✅ {table}: {purpose}")
                else:
                    self.log(f"   ❌ {table}: {purpose} - MISSING!")
                    all_present = False
            
            return all_present
    
    def export_schema(self, filename=None):
        """Export schema information to JSON"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"/app/schema_export_{timestamp}.json"
        
        with self.app.app_context():
            inspector = inspect(db.engine)
            schema = {
                'exported_at': datetime.now().isoformat(),
                'database_url': str(db.engine.url).replace('://', '://***@'),  # Hide password
                'tables': {}
            }
            
            for table_name in inspector.get_table_names():
                schema['tables'][table_name] = {
                    'columns': inspector.get_columns(table_name),
                    'foreign_keys': inspector.get_foreign_keys(table_name),
                    'indexes': [
                        {'name': idx['name'], 'columns': idx['column_names']}
                        for idx in inspector.get_indexes(table_name)
                    ]
                }
            
            # Save to file
            with open(filename, 'w') as f:
                json.dump(schema, f, indent=2, default=str)
            
            self.log(f"\n✅ Schema exported to: {filename}")
            return filename
    
    def generate_documentation(self):
        """Generate markdown documentation of the database schema"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        doc = f"""# AFCON360 Database Schema Documentation
Generated: {timestamp}

## Overview
This document provides a complete overview of the AFCON360 database schema.

## Table Statistics
- **Total Tables**: {len(self.tables)}
- **Last Inspected**: {timestamp}

## Tables

"""
        with self.app.app_context():
            inspector = inspect(db.engine)
            
            for table_name in sorted(inspector.get_table_names()):
                doc += f"### `{table_name}`\n\n"
                
                # Columns
                columns = inspector.get_columns(table_name)
                doc += "| Column | Type | Nullable | Default |\n"
                doc += "|--------|------|----------|---------|\n"
                for col in columns:
                    doc += f"| {col['name']} | {col['type']} | {col['nullable']} | {col.get('default', '')} |\n"
                
                doc += "\n"
                
                # Foreign Keys
                fks = inspector.get_foreign_keys(table_name)
                if fks:
                    doc += "**Foreign Keys:**\n\n"
                    for fk in fks:
                        doc += f"- `{fk['constrained_columns']}` → `{fk['referred_table']}.{fk['referred_columns']}`\n"
                    doc += "\n"
                
                doc += "---\n\n"
        
        # Save documentation
        doc_file = f"/app/database_schema_{datetime.now().strftime('%Y%m%d')}.md"
        with open(doc_file, 'w') as f:
            f.write(doc)
        
        self.log(f"\n✅ Documentation saved to: {doc_file}")
        return doc_file

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Database Table Inspector')
    parser.add_argument('--detail', action='store_true', help='Show detailed column info')
    parser.add_argument('--export', action='store_true', help='Export schema to JSON')
    parser.add_argument('--docs', action='store_true', help='Generate markdown documentation')
    parser.add_argument('--quiet', action='store_true', help='Suppress verbose output')
    
    args = parser.parse_args()
    
    inspector = TableInspector(verbose=not args.quiet)
    
    # Discover tables
    tables = inspector.discover_all_tables()
    
    # Check critical tables
    inspector.check_critical_tables()
    
    # Export if requested
    if args.export:
        inspector.export_schema()
    
    if args.docs:
        inspector.generate_documentation()
    
    # Success indicator
    print("\n" + "=" * 70)
    print("✅ Database inspection complete!")
    print("=" * 70)

if __name__ == "__main__":
    main()
