from app import create_app
from app.events.constants import EventStatus
from app.events.models import Event

print("=== COMPARING MODEL VS ENUM ===\n")

# Check what EventStatus values exist
print(f"EventStatus has {len(EventStatus)} values: {[s.value for s in EventStatus]}")

# Check what the model's status column accepts
col = Event.status.property.columns[0]
if hasattr(col.type, 'enum_class'):
    print(f"\nModel's enum_class: {col.type.enum_class}")
    print(f"Model's enum values: {[e.value for e in col.type.enum_class]}")
else:
    print(f"\nModel type: {col.type}")
    
# Check the actual database column type
from sqlalchemy import inspect, text
inspector = inspect(db.engine)
events_cols = inspector.get_columns('events')
for col_info in events_cols:
    if col_info['name'] == 'status':
        print(f"\nDatabase status type: {col_info['type']}")
        print(f"Database nullable: {col_info['nullable']}")
        print(f"Database default: {col_info.get('default')}")
