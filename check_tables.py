import os
os.environ['FLASK_APP'] = 'app.py'
from app import create_app
app = create_app()
with app.app_context():
    from app.extensions import db
    from sqlalchemy import text
    result = db.session.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE '%onboard%'")).fetchall()
    for r in result:
        print(r)