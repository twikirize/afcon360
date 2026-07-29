from app import create_app
from sqlalchemy import text
app = create_app()
with app.app_context():
    from app.extensions import db
    result = db.session.execute(text("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_property_status_valid'"))
    for row in result:
        print(row)