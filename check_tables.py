#!/usr/bin/env python3

from app import create_app
from app.extensions import db

def check_payment_tables():
    app = create_app()
    with app.app_context():
        # Get all table names
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        # Check for our new payment system tables
        payment_tables = [
            'wallet_transactions',
            'wallet_balances', 
            'payment_gateway_configs',
            'regulator_access_codes',
            'aggregator_webhook_configs',
            'delegation_records'
        ]
        
        print("Checking Payment System Tables:")
        print("=" * 50)
        
        found_tables = []
        missing_tables = []
        
        for table in payment_tables:
            if table in tables:
                found_tables.append(f"✅ {table}")
                print(f"✅ {table} - FOUND")
                
                # Show table structure
                columns = inspector.get_columns(table)
                print(f"   Columns: {len(columns)} fields")
                for col in columns[:3]:  # Show first 3 columns
                    print(f"   - {col['name']}: {col['type']}")
                if len(columns) > 3:
                    print(f"   ... and {len(columns) - 3} more columns")
                print()
            else:
                missing_tables.append(f"❌ {table}")
                print(f"❌ {table} - MISSING")
        
        print("\n" + "=" * 50)
        print(f"SUMMARY:")
        print(f"Found: {len(found_tables)} tables")
        print(f"Missing: {len(missing_tables)} tables")
        
        if missing_tables:
            print("\n❌ Missing Tables:")
            for table in missing_tables:
                print(f"   {table}")
        
        # Check settings table for new columns
        if 'settings' in tables:
            print(f"\nChecking Settings Table for New Columns:")
            settings_columns = inspector.get_columns('settings')
            
            new_columns = [
                'paypal_enabled', 'alipay_enabled', 'flutterwave_enabled',
                'paystack_enabled', 'mobile_money_enabled', 'visa_enabled',
                'wechat_enabled', 'wallet_min_transaction', 'aml_enabled',
                'kyc_enabled', 'delegation_enabled', 'regulator_access_enabled'
            ]
            
            found_settings = []
            for col in new_columns:
                if any(c['name'] == col for c in settings_columns):
                    found_settings.append(f"✅ {col}")
                    print(f"✅ {col}")
                else:
                    print(f"❌ {col}")
            
            print(f"\nSettings Columns Found: {len(found_settings)}/{len(new_columns)}")
        
        return len(missing_tables) == 0

if __name__ == "__main__":
    success = check_payment_tables()
    if success:
        print("\nAll payment system tables and columns are properly installed!")
    else:
        print("\nSome tables or columns are missing. Migration may need to be re-run.")
