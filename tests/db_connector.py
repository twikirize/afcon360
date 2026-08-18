from app.extensions import db

def get_connection():
    """Return a SQLAlchemy connection inside an active app context."""
    return db.engine.connect()
