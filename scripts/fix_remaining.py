#!/usr/bin/env python3
"""Fix remaining tables by creating them in correct order"""

from app import create_app
from app.extensions import db
from sqlalchemy import inspect, text
import time

app = create_app()

with app.app_context():
    inspector = inspect(db.engine)
    
    # List of tables to create in order
    tables_to_create = [
        'organisations',
        'organisation_members',
        'organisation_controllers',
        'organisation_documents',
        'organisation_licenses',
        'organisation_verifications',
        'organisation_kyb_checks',
        'organisation_kyb_documents',
        'organisation_ubos',
        'organisation_audit_logs',
        'compliance_cases',
        'compliance_reports',
        'compliance_settings',
        'compliance_audit_logs',
        'events',
        'event_ticket_types',
        'event_registrations',
        'event_waitlist',
        'event_roles',
        'event_moderation_logs',
        'event_transfer_requests',
        'event_transfer_logs',
        'event_assignments',
        'event_themes',
        'event_payment_preferences',
        'discount_codes',
        'accommodation_properties',
        'accommodation_photos',
        'accommodation_amenities_master',
        'accommodation_property_amenities',
        'accommodation_rules',
        'accommodation_bookings',
        'accommodation_booking_history',
        'accommodation_blocked_dates',
        'accommodation_availability_rules',
        'accommodation_reviews',
        'kyc_records',
        'wallet_audit_logs',
        'ledger_entries'
    ]
    
    created = 0
    for table_name in tables_to_create:
        if inspector.has_table(table_name):
            print(f"⏭️  Already exists: {table_name}")
            continue
        
        try:
            # Get the table metadata
            table = db.metadata.tables.get(table_name)
            if table:
                table.create(db.engine, checkfirst=True)
                print(f"✅ Created: {table_name}")
                created += 1
            else:
                print(f"⚠️ No metadata for: {table_name}")
        except Exception as e:
            print(f"❌ Failed: {table_name} - {str(e)[:80]}")
    
    print(f"\n📊 Created {created} new tables")
    print(f"📊 Total tables now: {len(inspector.get_table_names())}")
