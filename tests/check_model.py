from app.events.models import Event
from sqlalchemy import inspect

print("=== MODEL EXPECTATIONS ===\n")
for col in inspect(Event).columns:
    print(f"{col.name}: {col.type}")
