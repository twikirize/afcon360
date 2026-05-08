#!/usr/bin/env python3

from app import create_app
from app.extensions import db

def verify_payment_system():
    app = create_app()
    with app.app_context():
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        print("PAYMENT SYSTEM VERIFICATION")
        print("=" * 50)
        
        # Check for our new payment system tables
        payment_tables = [
            'wallet_transactions',
            'wallet_balances', 
            'payment_gateway_configs',
            'regulator_access_codes',
            'aggregator_webhook_configs',
            'delegation_records'
        ]
        
        found_count = 0
        total_count = len(payment_tables)
        
        print("Checking Payment System Tables:")
        print("-" * 30)
        
        for table in payment_tables:
            if table in tables:
                found_count += 1
                print(f"+ {table} - FOUND")
                
                # Get column count
                columns = inspector.get_columns(table)
                print(f"  Columns: {len(columns)}")
                
                # Show primary key
                pk = inspector.get_pk_constraint(table)
                if pk:
                    print(f"  Primary Key: {pk['constrained_columns']}")
                
                # Show foreign keys
                fks = inspector.get_foreign_keys(table)
                if fks:
                    print(f"  Foreign Keys: {len(fks)}")
                    for fk in fks:
                        print(f"    - {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
                
                print()
            else:
                print(f"- {table} - MISSING")
                print()
        
        print("Settings Table Columns:")
        print("-" * 30)
        
        # Check settings table for new columns
        if 'settings' in tables:
            settings_columns = inspector.get_columns('settings')
            column_names = [col['name'] for col in settings_columns]
            
            new_columns = [
                'paypal_enabled', 'alipay_enabled', 'flutterwave_enabled',
                'paystack_enabled', 'mobile_money_enabled', 'visa_enabled',
                'wechat_enabled', 'wallet_min_transaction', 'aml_enabled',
                'kyc_enabled', 'delegation_enabled', 'regulator_access_enabled',
                'paypal_client_id', 'flutterwave_public_key', 'paystack_public_key',
                'mtn_ug_api_key', 'airtel_ug_api_key', 'mpesa_api_key',
                'visa_merchant_id', 'wechat_app_id', 'wallet_max_transaction',
                'wallet_daily_limit', 'wallet_monthly_limit', 'wallet_max_balance',
                'paypal_fee', 'alipay_fee', 'flutterwave_fee', 'paystack_fee',
                'mobile_money_fee', 'wallet_2fa_enabled', 'wallet_pin_threshold',
                'delegation_enabled', 'admin_delegation_approval', 'max_delegation_duration',
                'aml_threshold', 'kyc_required_level', 'regulator_access_enabled',
                'audit_retention_days'
            ]
            
            found_settings = 0
            for col in new_columns:
                if col in column_names:
                    found_settings += 1
                    print(f"+ {col}")
                else:
                    print(f"- {col}")
            
            print(f"\nSettings Columns: {found_settings}/{len(new_columns)} found")
        
        print("\n" + "=" * 50)
        print(f"SUMMARY:")
        print(f"Payment Tables: {found_count}/{total_count} created")
        print(f"Total Database Tables: {len(tables)}")
        
        if found_count == total_count:
            print("PAYMENT SYSTEM MIGRATION SUCCESSFUL!")
        else:
            print("PAYMENT SYSTEM MIGRATION INCOMPLETE!")
        
        return found_count == total_count

if __name__ == "__main__":
    verify_payment_system()
