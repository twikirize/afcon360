"""
AFCON 360 Self-Healing Migration Generator
Performs deep inspection and generates a 'Repair' migration to fix:
1. Missing created_at/updated_at
2. Integer -> BigInteger upgrades
3. Missing Indexes on Foreign Keys
"""

import os
import sys
import uuid
from sqlalchemy import inspect
from flask import Flask

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from app.config import Config
from app.extensions import db

def generate_repair_migration():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        upgrade_lines = []

        print("\n🛠  Analyzing DB for repairs...")

        for table in tables:
            if table == 'alembic_version': continue

            columns = inspector.get_columns(table)
            col_names = [c['name'] for c in columns]

            # 1. TIMESTAMPS
            for ts in ['created_at', 'updated_at']:
                if ts not in col_names:
                    print(f"  [+] Missing {ts} in {table}")
                    upgrade_lines.append(f"    op.add_column('{table}', sa.Column('{ts}', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')))")
                    upgrade_lines.append(f"    op.create_index('ix_{table}_{ts}', '{table}', ['{ts}'], unique=False)")

            # 2. BIGINT UPGRADES
            for col in columns:
                c_name = col['name']
                c_type = str(col['type']).upper()
                # Upgrade PKs and columns ending in _id (excluding public identifiers)
                if (c_name == 'id' or c_name.endswith('_id')) and 'INT' in c_type and 'BIGINT' not in c_type:
                    if c_name not in ['user_id', 'org_id', 'public_id']:
                        print(f"  [^] Upgrading {table}.{c_name} to BIGINT")
                        upgrade_lines.append(f"    op.execute('ALTER TABLE \"{table}\" ALTER COLUMN {c_name} TYPE BIGINT USING {c_name}::bigint')")

            # 3. INDEXES
            fks = inspector.get_foreign_keys(table)
            existing_idxs = []
            for i in inspector.get_indexes(table):
                if i['column_names']:
                    existing_idxs.append(i['column_names'][0])

            for fk in fks:
                fk_col = fk['constrained_columns'][0]
                if fk_col not in existing_idxs:
                    print(f"  [#] Indexing FK {table}.{fk_col}")
                    upgrade_lines.append(f"    op.create_index('ix_{table}_{fk_col}', '{table}', ['{fk_col}'], unique=False)")

        if not upgrade_lines:
            print("\n✅ Database is healthy. No repairs needed.")
            return

        # Write the migration file
        rev_id = uuid.uuid4().hex[:12]
        # Use absolute path for migration file
        migrations_dir = os.path.join(PROJECT_ROOT, 'migrations', 'versions')
        if not os.path.exists(migrations_dir):
            os.makedirs(migrations_dir)

        filename = os.path.join(migrations_dir, f"{rev_id}_auto_architecture_repair.py")

        # Manually find the current head to avoid alembic.ini lookup issues
        from alembic.script import ScriptDirectory
        from alembic.config import Config as AlembicConfig

        # Explicitly set the migration scripts location
        migrations_path = os.path.join(PROJECT_ROOT, 'migrations')
        config = AlembicConfig()
        config.set_main_option("script_location", migrations_path)

        script = ScriptDirectory.from_config(config)
        head = script.get_current_head()

        content = f'''"""auto_architecture_repair

Revision ID: {rev_id}
Revises: {head}
Create Date: 2026-04-08

"""
from alembic import op
import sqlalchemy as sa

revision = '{rev_id}'
down_revision = '{head}'
branch_labels = None
depends_on = None

def upgrade():
{chr(10).join(upgrade_lines)}

def downgrade():
    pass
'''
        with open(filename, 'w') as f:
            f.write(content)

        print(f"\n🚀 SUCCESS: Generated migration {filename}")
        print("Now run: flask db upgrade")

if __name__ == '__main__':
    generate_repair_migration()
