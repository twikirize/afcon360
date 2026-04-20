# check_events.py - Save in project root (C:\Users\ADMIN\Desktop\afcon360_app\)

from app import create_app
from app.extensions import db
from sqlalchemy import inspect, text


def check_events():
    app = create_app()
    with app.app_context():
        print("\n" + "=" * 80)
        print("📊 EVENTS TABLE INSPECTION")
        print("=" * 80)

        inspector = inspect(db.engine)
        columns = inspector.get_columns('events')

        print("\n📋 ALL COLUMNS IN events TABLE:")
        print("-" * 40)
        for col in columns:
            print(f"  {col['name']:30} {str(col['type']):20} nullable={col['nullable']}")

        print("\n🏷️ ENUM TYPES IN DATABASE:")
        print("-" * 40)
        result = db.session.execute(text("""
            SELECT typname FROM pg_type
            WHERE typname IN ('creatortype', 'ownertype', 'transferstatus', 'discounttype')
        """))
        enums = [row[0] for row in result]
        for enum in ['creatortype', 'ownertype', 'transferstatus', 'discounttype']:
            status = "✅ EXISTS" if enum in enums else "❌ MISSING"
            print(f"  {enum:20} {status}")

        print("\n📈 EVENT COUNTS:")
        print("-" * 40)
        result = db.session.execute(text("SELECT COUNT(*) FROM events"))
        total = result.scalar()
        print(f"  Total events: {total}")

        if total > 0:
            result = db.session.execute(text("SELECT COUNT(*) FROM events WHERE public_id IS NULL"))
            null_public = result.scalar()
            print(f"  Events with NULL public_id: {null_public}")

            result = db.session.execute(text("SELECT COUNT(*) FROM events WHERE current_owner_id IS NULL"))
            null_owner = result.scalar()
            print(f"  Events with NULL current_owner_id: {null_owner}")

        print("\n📝 SAMPLE EVENT DATA:")
        print("-" * 40)
        result = db.session.execute(text("SELECT id, name, slug, organizer_id FROM events LIMIT 3"))
        for row in result:
            print(f"  ID: {row[0]}, Name: {row[1]}, Slug: {row[2]}, Organizer: {row[3]}")

        print("\n✅ Done!\n")


if __name__ == "__main__":
    check_events()
