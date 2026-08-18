import pytest
from sqlalchemy import or_, and_
from app.events.models import Event
from app.identity.models import Organisation
from app.identity.models.user import User
from flask import url_for

import uuid

def test_organisation_events_filtering(client, db_session):
    """Test that events are properly filtered on the organisation events dashboard"""
    unique_suffix = str(uuid.uuid4())[:8]
    test_user_id = str(uuid.uuid4())
    test_org_id = str(uuid.uuid4())
    # Create test user
    test_user = User(
        email=f"test_org_user_{unique_suffix}@example.com",
        password_hash="hashed",
        public_id=test_user_id,
        is_active=True
    )
    db_session.add(test_user)
    db_session.commit()
    # Create an organisation
    org = Organisation(
        legal_name=f"Test Org {unique_suffix}",
        org_id=test_org_id,
        country="US"
    )
    db_session.add(org)
    db_session.commit()
    org_id = org.id
    
    # Create various events
    
    # 1. Event owned by organisation
    event1 = Event(
        name="Org Owned Event",
        slug=f"org-owned-{unique_suffix}",
        city="Test City",
        organizer_id=test_user.id,
        current_owner_type='organization',
        current_owner_id=org_id,
        created_by_type='individual',
        created_by_id=test_user.id
    )
    
    # 2. Event operated by organisation (organization_id set)
    event2 = Event(
        name="Org Operated Event",
        slug=f"org-operated-{unique_suffix}",
        city="Test City",
        organizer_id=test_user.id,
        organization_id=org_id,
        current_owner_type='individual',
        current_owner_id=test_user.id,
        created_by_type='individual',
        created_by_id=test_user.id
    )
    
    # 3. Legacy event created by organisation (before ownership migration)
    event3 = Event(
        name="Org Created Event",
        slug=f"org-created-{unique_suffix}",
        city="Test City",
        organizer_id=test_user.id,
        created_by_type='organization',
        created_by_entity_id=org_id,
        current_owner_type='individual', # Suppose not yet migrated
        current_owner_id=test_user.id
    )

    # 4. Unrelated event
    event4 = Event(
        name="Unrelated Event",
        slug=f"unrelated-{unique_suffix}",
        city="Test City",
        organizer_id=test_user.id,
        current_owner_type='individual',
        current_owner_id=test_user.id,
        created_by_type='individual',
        created_by_id=test_user.id
    )
    
    db_session.add_all([event1, event2, event3, event4])
    db_session.commit()

    e1_id = event1.id
    e2_id = event2.id
    e3_id = event3.id
    e4_id = event4.id

    # MIGRATED LOGIC (matches app.identity.routes):
    events = Event.query.filter(
        Event.is_deleted.is_(False),
        or_(
            Event.organization_id == org_id,
            and_(
                Event.current_owner_type == 'organization',
                Event.current_owner_id == org_id,
            ),
        ),
    ).all()
    
    event_ids = [e.id for e in events]
    # Migration step: event3 was selected by created_by_type, but we are removing that fallback
    # so event3 should no longer be included.
    assert e1_id in event_ids
    assert e2_id in event_ids
    assert e3_id not in event_ids
    assert e4_id not in event_ids
