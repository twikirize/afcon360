from app import create_app
from app.events.models import Event
import inspect

app = create_app()
with app.app_context():
    # Get the actual column definition
    col = Event.status.property.columns[0]
    print(f"Column name: {col.name}")
    print(f"Column type: {col.type}")
    print(f"Type class: {col.type.__class__.__name__}")
    print(f"Type module: {col.type.__class__.__module__}")
    
    # Check if it's SQLAlchemy's Enum
    from sqlalchemy import Enum
    print(f"Is SA Enum: {isinstance(col.type, Enum)}")
    
    # Check the model file directly
    import ast
    with open('app/events/models.py', 'r') as f:
        content = f.read()
        # Find the Event class and its status column
        import re
        event_match = re.search(r'class Event\(.*?\):\s+(.*?)(?=\nclass|\Z)', content, re.DOTALL)
        if event_match:
            status_match = re.search(r'status\s*=\s*Column\([^)]+\)', event_match.group(1))
            if status_match:
                print(f'\nModel status definition: {status_match.group(0)[:200]}')
