# app/fan/migrate_fan_to_profile.py
"""
One-time migration: old Fan model → new FanProfile model.
Run AFTER: flask db migrate && flask db upgrade

Usage:
    flask shell
    >>> from app.fan.migrate_fan_to_profile import run_migration
    >>> run_migration()
"""

from datetime import datetime
from app.extensions import db


def run_migration(dry_run=True):
    """
    Migrate existing Fan records to FanProfile.
    Set dry_run=False to actually commit.
    """
    # Import old model — only works if fans table still exists
    try:
        from app.fan.models import Fan  # old model
    except ImportError:
        print("ERROR: Cannot import old Fan model. Has it already been deleted?")
        return

    from app.fan.models import FanProfile

    old_fans = Fan.query.all()
    print(f"Found {len(old_fans)} fan records to migrate.")

    migrated = 0
    skipped = 0

    for fan in old_fans:
        existing = FanProfile.query.filter_by(user_id=fan.user_id).first()
        if existing:
            print(f"  SKIP user_id={fan.user_id} — FanProfile already exists")
            skipped += 1
            continue

        profile = FanProfile(
            user_id=fan.user_id,
            is_active=True,
            favorite_teams=getattr(fan, 'favorite_teams', '[]') or '[]',
            favorite_sports='["football"]',
            tournament_notifications=True,
            match_reminders=True,
            team_news=True,
            social_features_enabled=True,
            activated_at=getattr(fan, 'created_at', datetime.utcnow()),
        )
        db.session.add(profile)
        migrated += 1
        print(f"  MIGRATE user_id={fan.user_id}")

    if dry_run:
        print(f"\nDRY RUN complete. Would migrate {migrated}, skip {skipped}.")
        print("Run with dry_run=False to commit.")
        db.session.rollback()
    else:
        db.session.commit()
        print(f"\nMigration complete. Migrated: {migrated}, Skipped: {skipped}.")
        print("Verify data, then drop the old 'fans' table manually.")
