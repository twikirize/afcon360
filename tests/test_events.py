import pytest
from app.config import TestingConfig

def test_get_event_not_found(test_db):
    from app.events.services import EventService
    result = EventService.get_event('this-slug-does-not-exist-xyz')
    assert result is None, f"Expected None for unknown slug, got: {result}"


def test_get_event_returns_expected_fields(test_db):
    from app.events.services import EventService
    from app.events.models import Event, OwnerType, CreatorType
    from app.identity.models.user import User
    from datetime import datetime, timezone, timedelta
    
    # create a dummy user
    import uuid
    dummy_user = User(public_id=str(uuid.uuid4()), email=f"dummy_{uuid.uuid4().hex}@test.com", password_hash="dummy")
    test_db.add(dummy_user)
    test_db.commit()
    
    import uuid
    slug_val = f"nothing-{uuid.uuid4().hex[:8]}"
    event = Event(
        name="Nothing Event",
        slug=slug_val,
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=1),
        status="published",
        category="conference",
        city="Test City",
        organizer_id=dummy_user.id,
        current_owner_type=OwnerType.INDIVIDUAL,
        current_owner_id=dummy_user.id,
        created_by_type=CreatorType.INDIVIDUAL,
        created_by_id=dummy_user.id
    )
    test_db.add(event)
    test_db.commit()
    
    result = EventService.get_event(slug_val)  # real event in DB
    assert result is not None, "Expected event with slug 'nothing' to exist"

    # Fields that MUST be present
    assert 'id' in result,          "Missing 'id' (public_id)"
    assert 'slug' in result,        "Missing 'slug'"
    assert 'name' in result,        "Missing 'name'"

    # Fields that MUST NOT be present
    assert 'internal_id' not in result,    "internal_id must not be exposed"
    assert 'approved_by_id' not in result, "approved_by_id must not be exposed"

    # id must be a UUID string, not an integer
    assert isinstance(result['id'], str), "id must be a UUID string, not an int"
    assert len(result['id']) == 36,       "id must be a valid UUID (36 chars)"

    # website must never be empty string
    assert result.get('website') != '', "website should be None not empty string"

    print('\nAPI response fields:')
    for k, v in result.items():
        if k != 'ticket_types':
            print(f'  {k:<25}: {v}')
    print(f'  ticket_types: {len(result["ticket_types"])} type(s)')
