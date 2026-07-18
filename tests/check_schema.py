from app import create_app
from app.extensions import db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    # Check idempotency_keys table structure
    inspector = inspect(db.engine)
    columns = inspector.get_columns('idempotency_keys')
    print('Current idempotency_keys columns:')
    for col in columns:
        print(f"  {col['name']}: {col['type']}")
    
    # Check the model
    from app.models.idempotency_key import IdempotencyKey
    print(f'\nModel expects id type: {IdempotencyKey.id.type}')
