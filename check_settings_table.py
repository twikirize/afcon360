#!/usr/bin/env python3

from app import create_app
from app.extensions import db

def check_settings_table():
    app = create_app()
    with app.app_context():
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        print("Looking for settings table:")
        print("=" * 40)
        
        # Look for any table with 'setting' in the name
        setting_tables = [t for t in tables if 'setting' in t.lower()]
        
        if setting_tables:
            print(f"Found settings tables: {setting_tables}")
            for table in setting_tables:
                columns = inspector.get_columns(table)
                print(f"\n{table}:")
                print(f"  Columns: {len(columns)}")
                for col in columns[:5]:  # Show first 5 columns
                    print(f"  - {col['name']}: {col['type']}")
                if len(columns) > 5:
                    print(f"  ... and {len(columns) - 5} more columns")
        else:
            print("No settings table found!")
            
            # Show all tables to help identify the correct one
            print(f"\nAll tables in database ({len(tables)}):")
            print("-" * 30)
            for i, table in enumerate(sorted(tables)):
                if i < 20:  # Show first 20 tables
                    print(f"  {table}")
                elif i == 20:
                    print(f"  ... and {len(tables) - 20} more tables")
                    break

if __name__ == "__main__":
    check_settings_table()
