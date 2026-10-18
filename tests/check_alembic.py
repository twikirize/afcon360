from app import create_app
from app.extensions import db
from flask_migrate import Migrate
from flask import Flask
import os

# Create minimal app to see differences
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from app.extensions import db
db.init_app(app)

from flask_migrate import Migrate
migrate = Migrate(app, db)

# Import all models to register them
from app.events.models import Event, EventHostRegistration
from app.accommodation.models.property import Property

with app.app_context():
    print("Import models to see what Alembic detects...")
    
