"""
One-time migration: copy FanProfile data into UserProfile new columns.
Run with: flask shell < scripts/migrate_fan_profiles.py
"""
from app.extensions import db
from sqlalchemy import text

rows = db.session.execute(text("""
    SELECT
        fp.user_id,
        fp.display_name,
        fp.avatar_url,
        fp.bio,
        fp.nationality
    FROM fan_profiles fp
""")).fetchall()

print(f"Migrating {len(rows)} FanProfile records...")

for row in rows:
    # fan_profiles.user_id is the internal BIGINT users.id
    # UserProfile.user_id is users.public_id (UUID string)
    # We need to join through users table
    user_public_id = db.session.execute(
        text("SELECT public_id FROM users WHERE id = :uid"),
        {"uid": row.user_id}
    ).scalar()

    if not user_public_id:
        print(f"  SKIP: no user found for fan_profiles.user_id={row.user_id}")
        continue

    db.session.execute(text("""
        UPDATE user_profiles SET
            display_name = COALESCE(display_name, :display_name),
            avatar_url   = COALESCE(avatar_url, :avatar_url),
            bio          = COALESCE(bio, :bio)
        WHERE user_id = :public_id
    """), {
        "display_name": row.display_name,
        "avatar_url":   row.avatar_url,
        "bio":          row.bio,
        "public_id":    user_public_id,
    })

    # nationality already exists on UserProfile — only copy if empty
    if row.nationality:
        db.session.execute(text("""
            UPDATE user_profiles SET nationality = :nat
            WHERE user_id = :public_id AND (nationality IS NULL OR nationality = '')
        """), {"nat": row.nationality, "public_id": user_public_id})

    print(f"  OK: migrated fan_profile for user {user_public_id}")

db.session.commit()
print("Migration complete.")
