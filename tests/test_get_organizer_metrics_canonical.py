import pytest
from app.events.metrics_service import EventMetricsService
from app.events.models import Event
import uuid

def test_get_organizer_metrics_canonical(test_db):
    """Test get_organizer_metrics retrieves metrics correctly for canonical ownership"""
    from app.identity.models.user import User
    
    # 1. Create a user
    user = User(email=f"metrics_user_{uuid.uuid4().hex[:8]}@test.com", password_hash="hashed", public_id=str(uuid.uuid4()), is_active=True)
    test_db.add(user)
    test_db.commit()
    
    # 2. Create events for the user
    # Canonical owner event
    event1 = Event(
        name="Metrics Event 1",
        slug=f"metrics-event-1-{uuid.uuid4().hex[:8]}",
        city="Test City",
        organizer_id=user.id,
        current_owner_type='individual',
        current_owner_id=user.id,
        created_by_type='individual',
        created_by_id=user.id
    )
    test_db.add(event1)
    test_db.commit()
    
    metrics = EventMetricsService.get_organizer_metrics(user.id)
    assert metrics['total_events'] >= 1
    assert 'event_breakdown' in metrics
