#!/usr/bin/env python
"""
Fix Owner Role Assignment Script
Run: python fix_owner.py
"""

import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from sqlalchemy import text


def fix_owner_role():
    """Fix owner role assignment by checking table structure first"""

    app = create_app()

    with app.app_context():
        print("\n" + "=" * 60)
        print("🔧 FIXING OWNER ROLE ASSIGNMENT")
        print("=" * 60)

        EMAIL = "twikirizeobed@gmail.com"

        # Step 1: Find the user
        print("\n📋 Step 1: Finding user...")
        user = db.session.execute(
            text("SELECT id, username FROM users WHERE email = :email"),
            {"email": EMAIL}
        ).fetchone()

        if not user:
            print(f"❌ User not found: {EMAIL}")
            return False

        user_id, username = user
        print(f"   ✅ Found user: {username} (ID: {user_id})")

        # Step 2: Find owner role
        print("\n📋 Step 2: Finding owner role...")
        owner_role = db.session.execute(
            text("SELECT id FROM roles WHERE name = 'owner'")
        ).fetchone()

        if not owner_role:
            print("❌ Owner role not found!")
            return False

        role_id = owner_role[0]
        print(f"   ✅ Owner role ID: {role_id}")

        # Step 3: Check user_roles table structure
        print("\n📋 Step 3: Checking user_roles table structure...")
        columns = db.session.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'user_roles'
            ORDER BY ordinal_position
        """)).fetchall()

        col_names = [c[0] for c in columns]
        print(f"   Columns in user_roles: {col_names}")

        # Step 4: Build INSERT statement based on actual columns
        print("\n📋 Step 4: Assigning owner role...")

        # Base columns that should always exist
        insert_cols = ['user_id', 'role_id']
        insert_values = {'uid': user_id, 'rid': role_id}

        # Add optional columns if they exist
        if 'assigned_at' in col_names:
            insert_cols.append('assigned_at')
            insert_values['assigned_at'] = 'NOW()'

        if 'created_at' in col_names:
            insert_cols.append('created_at')
            insert_values['created_at'] = 'NOW()'

        if 'updated_at' in col_names:
            insert_cols.append('updated_at')
            insert_values['updated_at'] = 'NOW()'

        if 'assigned_by' in col_names:
            insert_cols.append('assigned_by')
            insert_values['assigned_by'] = user_id

        # Build the INSERT statement
        cols_str = ', '.join(insert_cols)
        vals_str = ', '.join([f':{c}' for c in insert_cols if c not in ['assigned_at', 'created_at', 'updated_at']])

        # Handle special case for NOW() values
        now_columns = []
        for col in ['assigned_at', 'created_at', 'updated_at']:
            if col in insert_cols:
                now_columns.append(col)

        if now_columns:
            now_str = ', '.join(now_columns)
            sql = f"""
                INSERT INTO user_roles ({cols_str})
                SELECT
                    :uid,
                    :rid,
                    {', '.join(['NOW()' for _ in now_columns]) if now_columns else ''}
                WHERE NOT EXISTS (
                    SELECT 1 FROM user_roles WHERE user_id = :uid AND role_id = :rid
                )
            """
        else:
            sql = f"""
                INSERT INTO user_roles ({cols_str})
                SELECT :uid, :rid
                WHERE NOT EXISTS (
                    SELECT 1 FROM user_roles WHERE user_id = :uid AND role_id = :rid
                )
            """

        # Clean up SQL (remove extra commas, etc.)
        sql = sql.replace(', ,', ',').replace('( ,', '(').replace(', )', ')')

        try:
            result = db.session.execute(text(sql), insert_values)
            db.session.commit()

            if result.rowcount > 0:
                print(f"   ✅ Owner role successfully assigned to {username}!")
            else:
                print(f"   ⚠️ Owner role already assigned to {username} (no changes made)")

        except Exception as e:
            db.session.rollback()
            print(f"   ❌ Error: {e}")

            # Fallback: Try a simpler approach
            print("\n📋 Trying fallback approach...")
            try:
                # Get all columns that are NOT NULL and have no default
                required_cols = db.session.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'user_roles'
                    AND is_nullable = 'NO'
                    AND column_default IS NULL
                    AND column_name NOT IN ('id')
                """)).fetchall()

                if required_cols:
                    req_names = [c[0] for c in required_cols]
                    print(f"   Required columns: {req_names}")

                    # Build INSERT with required columns only
                    placeholders = ', '.join([f':{c}' for c in req_names])
                    cols_str = ', '.join(req_names)

                    values = {}
                    for col in req_names:
                        if col == 'user_id':
                            values[col] = user_id
                        elif col == 'role_id':
                            values[col] = role_id
                        elif col in ['assigned_at', 'created_at', 'updated_at']:
                            values[col] = datetime.now(timezone.utc)
                        elif col == 'assigned_by':
                            values[col] = user_id
                        else:
                            values[col] = None

                    sql = f"""
                        INSERT INTO user_roles ({cols_str})
                        VALUES ({placeholders})
                        ON CONFLICT (user_id, role_id) DO NOTHING
                    """

                    db.session.execute(text(sql), values)
                    db.session.commit()
                    print(f"   ✅ Owner role assigned (fallback method)!")

            except Exception as e2:
                db.session.rollback()
                print(f"   ❌ Fallback also failed: {e2}")
                return False

        # Step 5: Verify
        print("\n📋 Step 5: Verifying assignment...")
        verify = db.session.execute(text("""
            SELECT r.name
            FROM user_roles ur
            JOIN roles r ON ur.role_id = r.id
            WHERE ur.user_id = :uid
        """), {"uid": user_id}).fetchall()

        if verify:
            print(f"   ✅ User {username} has roles: {[v[0] for v in verify]}")
        else:
            print(f"   ⚠️ No roles found for {username}")

        print("\n" + "=" * 60)
        print("✅ COMPLETE!")
        print("=" * 60)
        return True


if __name__ == "__main__":
    from datetime import datetime, timezone

    fix_owner_role()
