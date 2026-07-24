#!/usr/bin/env python
"""
Fix missing system_configs table
Run: python scripts/create_system_configs.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.extensions import db
from sqlalchemy import text

def create_system_configs():
    app = create_app()
    with app.app_context():
        try:
            inspector = db.inspect(db.engine)
            if 'system_configs' in inspector.get_table_names():
                print("system_configs table already exists")
                return

            print("Creating system_configs table...")

            db.session.execute(text("""
                CREATE TABLE system_configs (
                    id BIGSERIAL PRIMARY KEY,
                    key VARCHAR(100) NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT,
                    created_by BIGINT,
                    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
                    deleted_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY (created_by) REFERENCES users(id),
                    CONSTRAINT uq_system_configs_key UNIQUE (key)
                )
            """))

            db.session.execute(text("CREATE INDEX ix_system_configs_created_at ON system_configs(created_at)"))
            db.session.execute(text("CREATE INDEX ix_system_configs_is_deleted ON system_configs(is_deleted)"))
            db.session.execute(text("CREATE INDEX ix_system_configs_key ON system_configs(key)"))
            db.session.execute(text("CREATE INDEX ix_system_configs_updated_at ON system_configs(updated_at)"))

            db.session.commit()
            print("system_configs table created successfully")

        except Exception as e:
            db.session.rollback()
            print(f"Error: {e}")
            raise

if __name__ == "__main__":
    create_system_configs()
