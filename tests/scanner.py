# check_all_dependencies.py
from app import create_app
from app.config import TestingConfig
from app.extensions import db
from sqlalchemy import MetaData, func, inspect, select

app = create_app(config_object=TestingConfig)

with app.app_context():
    print("=" * 60)
    print("FULL DATABASE DEPENDENCY SCANNER")
    print("=" * 60)

    # Get all tables in database
    inspector = inspect(db.engine)
    all_tables = inspector.get_table_names()

    # Tables we're concerned about
    suspect_tables = [
        'manageable_items',
        'content_submissions',
        'manageable_categories',
        'user_dashboard_configs',
        'server_sessions'
    ]

    for suspect in suspect_tables:
        if suspect not in all_tables:
            print(f"\n❌ Table '{suspect}' does NOT exist in database")
            continue

        print(f"\n📋 TABLE: {suspect}")
        print("-" * 40)

        # 1. Find tables that DEPEND ON this table through reflected foreign keys
        dependents = [
            (table, foreign_key.get('name'))
            for table in all_tables
            for foreign_key in inspector.get_foreign_keys(table)
            if foreign_key.get('referred_table') == suspect
        ]
        if dependents:
            print(f"  ⚠️ Tables that DEPEND ON '{suspect}':")
            for dependent_table, constraint_name in dependents:
                print(f"     - {dependent_table} (via {constraint_name})")
        else:
            print(f"  ✅ No tables depend on '{suspect}'")

        # 2. Find tables THIS TABLE depends on
        references = inspector.get_foreign_keys(suspect)
        if references:
            print(f"  📌 '{suspect}' references:")
            for foreign_key in references:
                print(f"     - {foreign_key.get('referred_table')}")

        metadata = MetaData()
        metadata.reflect(bind=db.engine, only=[suspect])

        if suspect in metadata.tables:
            columns = [c.name for c in metadata.tables[suspect].columns]
            print(f"  📊 Columns in '{suspect}': {', '.join(columns[:10])}")
            if len(columns) > 10:
                print(f"     ... and {len(columns) - 10} more")
        else:
            print(f"  🔍 No SQLAlchemy model found for '{suspect}'")

        # 4. Check row count through the reflected table expression
        row_count = db.session.scalar(
            select(func.count()).select_from(metadata.tables[suspect])
        )
        print(f"  📈 Row count: {row_count}")

    print("\n" + "=" * 60)
    print("CROSS-MODULE DEPENDENCY CHECK")
    print("=" * 60)

    # Check for references from known modules
    modules_to_check = [
        'app.auth', 'app.identity', 'app.wallet', 'app.events',
        'app.accommodation', 'app.transport', 'app.tourism',
        'app.admin', 'app.fan', 'app.profile', 'app.kyc'
    ]

    for suspect in suspect_tables:
        print(f"\n🔍 Searching for '{suspect}' in codebase...")

        import os
        import re

        found_in = []
        for root, dirs, files in os.walk('app'):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if suspect in content:
                                # Check if it's a model reference
                                if re.search(rf'class.*{suspect}.*\(.*Model.*\)', content):
                                    found_in.append(f"{filepath} (as Model)")
                                elif re.search(rf'__tablename__.*=.*[\'"]{suspect}[\'"]', content):
                                    found_in.append(f"{filepath} (as __tablename__)")
                                elif suspect in content:
                                    found_in.append(filepath)
                    except:
                        pass

        if found_in:
            print(f"  ⚠️ Found in code:")
            for f in found_in[:5]:
                print(f"     - {f}")
        else:
            print(f"  ✅ No code references found")

    print("\n" + "=" * 60)
    print("RECOMMENDATION")
    print("=" * 60)
