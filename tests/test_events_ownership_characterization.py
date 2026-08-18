import uuid
import pytest
from datetime import datetime, timedelta, timezone

from app.events.permissions import _is_event_owner, resolve_user_roles
from app.events.models import Event, EventRole, OwnerType, CreatorType
from app.identity.models.user import User
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember, OrgRole, OrgUserRole
from unittest.mock import PropertyMock, patch

@pytest.fixture(autouse=True)
def mock_is_authenticated():
    with patch("app.identity.models.user.User.is_authenticated", new_callable=PropertyMock) as mock_auth:
        mock_auth.return_value = True
        yield mock_auth

@pytest.fixture
def char_user(test_db):
    user = User(
        email=f"char_{uuid.uuid4().hex}@test.com",
        public_id=str(uuid.uuid4()),
        password_hash="fake"
    )
    test_db.add(user)
    test_db.commit()
    return user

@pytest.fixture
def other_user(test_db):
    user = User(
        email=f"other_{uuid.uuid4().hex}@test.com",
        public_id=str(uuid.uuid4()),
        password_hash="fake"
    )
    test_db.add(user)
    test_db.commit()
    return user

@pytest.fixture
def char_org(test_db):
    org = Organisation(
        legal_name=f"Char Org {uuid.uuid4().hex}",
        org_id=str(uuid.uuid4()),
        country="UG",
        contact_email=f"char_org_{uuid.uuid4().hex}@test.com"
    )
    test_db.add(org)
    test_db.commit()
    return org

def test_current_organizer_based_owner(test_db, char_user):
    event = Event(
        name="Test Event Organizer",
        slug=f"evt-{uuid.uuid4().hex}",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=1),
        status="published",
        category="conference",
        city="Test City",
        organizer_id=char_user.id,
        created_by_type=CreatorType.INDIVIDUAL,
        created_by_id=char_user.id,
        current_owner_type=OwnerType.INDIVIDUAL,
        current_owner_id=char_user.id # Assuming standard creation
    )
    test_db.add(event)
    test_db.commit()

    assert _is_event_owner(char_user, event) is True
    roles = resolve_user_roles(char_user, event)
    assert 'organiser' in roles

def test_current_owner_based_owner(test_db, char_user, other_user):
    event = Event(
        name="Test Event Owner",
        slug=f"evt-{uuid.uuid4().hex}",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=1),
        status="published",
        category="conference",
        city="Test City",
        organizer_id=other_user.id, # different user
        created_by_type=CreatorType.INDIVIDUAL,
        created_by_id=other_user.id,
        current_owner_type=OwnerType.INDIVIDUAL,
        current_owner_id=char_user.id
    )
    test_db.add(event)
    test_db.commit()

    assert _is_event_owner(char_user, event) is True
    roles = resolve_user_roles(char_user, event)
    assert 'organiser' in roles

def test_creator_not_owner(test_db, char_user, other_user):
    event = Event(
        name="Test Event Creator Not Owner",
        slug=f"evt-{uuid.uuid4().hex}",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=1),
        status="published",
        category="conference",
        city="Test City",
        organizer_id=other_user.id,
        created_by_type=CreatorType.INDIVIDUAL,
        created_by_id=char_user.id,
        current_owner_type=OwnerType.INDIVIDUAL,
        current_owner_id=other_user.id
    )
    test_db.add(event)
    test_db.commit()

    assert _is_event_owner(char_user, event) is False
    roles = resolve_user_roles(char_user, event)
    assert 'organiser' not in roles


def test_canonical_owner_overrides_stale_organizer(test_db, char_user, other_user):
    """A transferred canonical owner must not be overridden by organizer_id."""
    event = Event(
        name="Test Event Stale Organizer",
        slug=f"evt-{uuid.uuid4().hex}",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=1),
        status="published",
        category="conference",
        city="Test City",
        organizer_id=char_user.id,
        created_by_type=CreatorType.INDIVIDUAL,
        created_by_entity_id=char_user.id,
        current_owner_type=OwnerType.INDIVIDUAL,
        current_owner_id=other_user.id,
    )
    test_db.add(event)
    test_db.commit()

    assert _is_event_owner(char_user, event) is False


def test_legacy_owner_fallback_without_canonical_owner(char_user):
    """Legacy payloads without canonical owner fields retain compatibility."""
    assert _is_event_owner(char_user, {"organizer_id": char_user.id}) is True


def test_organization_operator(test_db, char_user, char_org, other_user):
    member = OrganisationMember(
        user_id=char_user.id,
        organisation_id=char_org.id
    )
    test_db.add(member)
    test_db.commit()

    org_role = OrgRole(
        name="org_admin",
        organisation_id=char_org.id
    )
    test_db.add(org_role)
    test_db.commit()

    our = OrgUserRole(
        organisation_member_id=member.id,
        role_id=org_role.id
    )
    test_db.add(our)
    test_db.commit()

    event = Event(
        name="Test Event Org Operator",
        slug=f"evt-{uuid.uuid4().hex}",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=1),
        status="published",
        category="conference",
        city="Test City",
        organizer_id=other_user.id,
        organization_id=char_org.id,
        created_by_type=CreatorType.ORGANIZATION,
        created_by_id=char_org.id,
        current_owner_type=OwnerType.ORGANIZATION,
        current_owner_id=char_org.id
    )
    test_db.add(event)
    test_db.commit()

    # Fully reload user and their relationships for the assertion
    test_db.expire_all()
    char_user_reloaded = test_db.query(User).get(char_user.id)

    # The user is org_admin of the event's organisation.
    assert _is_event_owner(char_user_reloaded, event) is False # _is_event_owner only looks at INDIVIDUAL ownership/organizer
    
    from unittest.mock import patch
    from app.auth.context import ContextDescriptor, ContextType
    
    # Simulate that the user has actively selected the organisation context
    mock_context = ContextDescriptor(
        type=ContextType.ORGANISATION,
        public_id=char_org.org_id,
        label="Test Org",
        role="org_admin"
    )
    with patch("flask.has_request_context", return_value=True), \
         patch("app.auth.context.get_active_context", return_value=mock_context):
        roles = resolve_user_roles(char_user_reloaded, event)
    
    assert 'org_admin' in roles

    # Simulate selecting the Personal context instead
    mock_context_personal = ContextDescriptor(
        type=ContextType.PERSONAL,
        public_id=char_user_reloaded.public_id,
        label="Personal",
        role=None
    )
    with patch("flask.has_request_context", return_value=True), \
         patch("app.auth.context.get_active_context", return_value=mock_context_personal):
        roles_personal = resolve_user_roles(char_user_reloaded, event)
    
    assert 'org_admin' not in roles_personal

def test_event_role_operator(test_db, char_user, other_user):
    event = Event(
        name="Test Event Role Operator",
        slug=f"evt-{uuid.uuid4().hex}",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=1),
        status="published",
        category="conference",
        city="Test City",
        organizer_id=other_user.id,
        created_by_type=CreatorType.INDIVIDUAL,
        created_by_id=other_user.id,
        current_owner_type=OwnerType.INDIVIDUAL,
        current_owner_id=other_user.id
    )
    test_db.add(event)
    test_db.commit()

    event_role = EventRole(
        event_id=event.id,
        user_id=char_user.id,
        role="co_organizer"
    )
    test_db.add(event_role)
    test_db.commit()

    roles = resolve_user_roles(char_user, event)
    assert 'co_organizer' in roles
    assert 'organiser' not in roles

def test_super_admin_authority(test_db, char_user, other_user):
    from app.identity.models.roles_permission import Role
    from app.identity.models.user import UserRole
    from app.auth.context import ContextDescriptor, ContextType
    from unittest.mock import patch
    
    # 1. Give char_user super_admin global role
    role = test_db.query(Role).filter_by(name="super_admin", scope="global").first()
    if not role:
        role = Role(name="super_admin", scope="global")
        test_db.add(role)
        test_db.commit()
    
    ur = UserRole(user_id=char_user.id, role_id=role.id)
    test_db.add(ur)
    test_db.commit()
    
    # Reload user
    test_db.expire_all()
    char_user_reloaded = test_db.query(User).get(char_user.id)
    
    # Create an event they don't own and are not part of org
    event = Event(
        name="Test Event Super Admin",
        slug=f"evt-{uuid.uuid4().hex}",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=1),
        status="published",
        category="conference",
        city="Test City",
        organizer_id=other_user.id,
        created_by_type=CreatorType.INDIVIDUAL,
        created_by_id=other_user.id,
        current_owner_type=OwnerType.INDIVIDUAL,
        current_owner_id=other_user.id
    )
    test_db.add(event)
    test_db.commit()

    # Case 1: super_admin + PLATFORM context -> platform authority
    mock_platform = ContextDescriptor(
        type=ContextType.PLATFORM,
        public_id=None,
        label="Platform",
        role="super_admin"
    )
    with patch("flask.has_request_context", return_value=True), \
         patch("app.auth.context.get_active_context", return_value=mock_platform):
         roles = resolve_user_roles(char_user_reloaded, event)
    assert 'super_admin' in roles

    # Case 2: super_admin + AFCON context -> no super_admin leaked to org context
    mock_org = ContextDescriptor(
        type=ContextType.ORGANISATION,
        public_id=str(uuid.uuid4()), # Some org they don't belong to
        label="Some Org",
        role=None
    )
    with patch("flask.has_request_context", return_value=True), \
         patch("app.auth.context.get_active_context", return_value=mock_org):
         roles_org = resolve_user_roles(char_user_reloaded, event)
    assert 'super_admin' not in roles_org

    # Case 3: super_admin + PERSONAL context -> no super_admin leaked to personal context
    mock_personal = ContextDescriptor(
        type=ContextType.PERSONAL,
        public_id=char_user_reloaded.public_id,
        label="Personal",
        role=None
    )
    with patch("flask.has_request_context", return_value=True), \
         patch("app.auth.context.get_active_context", return_value=mock_personal):
         roles_personal = resolve_user_roles(char_user_reloaded, event)
    assert 'super_admin' not in roles_personal


def test_event_role_context_matching(test_db, char_user, char_org, other_user):
    from app.auth.context import ContextDescriptor, ContextType
    from unittest.mock import patch
    
    event = Event(
        name="Test Event Role Context",
        slug=f"evt-{uuid.uuid4().hex}",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=1),
        status="published",
        category="conference",
        city="Test City",
        organizer_id=other_user.id,
        created_by_type=CreatorType.INDIVIDUAL,
        created_by_id=other_user.id,
        current_owner_type=OwnerType.INDIVIDUAL,
        current_owner_id=other_user.id
    )
    test_db.add(event)
    test_db.commit()

    # Give EventRole assigned through an organisation
    event_role = EventRole(
        event_id=event.id,
        user_id=char_user.id,
        organisation_id=char_org.id,
        role="co_organizer"
    )
    test_db.add(event_role)
    test_db.commit()
    
    test_db.expire_all()
    char_user_reloaded = test_db.query(User).get(char_user.id)

    # If context is the matching organisation, they get the role
    mock_org_match = ContextDescriptor(
        type=ContextType.ORGANISATION,
        public_id=char_org.org_id,
        label="Matching Org",
        role=None
    )
    with patch("flask.has_request_context", return_value=True), \
         patch("app.auth.context.get_active_context", return_value=mock_org_match):
         roles_match = resolve_user_roles(char_user_reloaded, event)
    assert 'co_organizer' in roles_match

    # If context is a wrong organisation, they DO NOT get the role
    mock_org_wrong = ContextDescriptor(
        type=ContextType.ORGANISATION,
        public_id=str(uuid.uuid4()),
        label="Wrong Org",
        role=None
    )
    with patch("flask.has_request_context", return_value=True), \
         patch("app.auth.context.get_active_context", return_value=mock_org_wrong):
         roles_wrong = resolve_user_roles(char_user_reloaded, event)
    assert 'co_organizer' not in roles_wrong
    
    # If context is personal, they DO NOT get the role (since it's an org-assigned role)
    mock_personal = ContextDescriptor(
        type=ContextType.PERSONAL,
        public_id=char_user_reloaded.public_id,
        label="Personal",
        role=None
    )
    with patch("flask.has_request_context", return_value=True), \
         patch("app.auth.context.get_active_context", return_value=mock_personal):
         roles_personal = resolve_user_roles(char_user_reloaded, event)
    assert 'co_organizer' not in roles_personal
