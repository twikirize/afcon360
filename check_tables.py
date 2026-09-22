import os
os.environ['FLASK_ENV'] = 'testing'
os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@localhost:5432/afcon360_test'
from app import create_app
from app.extensions import db
from sqlalchemy import text
app = create_app()
with app.app_context():
    result = db.session.execute(text("SELECT table_schema, table_name FROM information_schema.tables WHERE table_name LIKE '%marketplace%'"))
    for row in result:
        print(row)