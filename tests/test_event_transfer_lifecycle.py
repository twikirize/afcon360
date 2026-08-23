import pytest
import uuid
from datetime import datetime, timezone, timedelta
from app.events.models import Event, CreatorType, OwnerType, EventTransferRequest, TransferStatus, EventTransferLog
from app.identity.models.user import User
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember, OrgRole, OrgUserRole
from app.events.services import EventService

@pytest.fixture
def transfer_user(test_db):
    user = User(
        public_id=str(uuid.uuid4()),
        email=f"transfer_{uuid.uuid4()}@example.com",
        password_hash="fakehash",
        is_active=True
    )
    test_db.add(user)
    test_db.commit()
    return user

@pytest.fixture
def target_user(test_db):
    user = User(
        public_id=str(uuid.uuid4()),
        email=f"target_{uuid.uuid4()}@example.com",
        password_hash="fakehash",
        is_active=True
    )
    test_db.add(user)
    test_db.commit()
    return user

@pytest.fixture
def target_org(test_db):
    org = Organisation(
        org_id=str(uuid.uuid4()),
        legal_name=f"Target Org {uuid.uuid4().hex}",
        country="UG"
    )
    test_db.add(org)
    test_db.commit()
    return org

@pytest.fixture
def test_event(test_db, transfer_user):
    event = Event(
        name="Test Transfer Event",
        slug=f"transfer-evt-{uuid.uuid4().hex}",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=1),
        status="published",
        category="conference",
        city="Test City",
        organizer_id=transfer_user.id,
        created_by_type=CreatorType.INDIVIDUAL,
        created_by_id=transfer_user.id,
        current_owner_type=OwnerType.INDIVIDUAL,
        current_owner_id=transfer_user.id
    )
    test_db.add(event)
    test_db.commit()
    return event

def test_request_event_transfer_success(test_db, transfer_user, target_user, test_event):
    success, err = EventService.request_event_transfer(
        event_slug=test_event.slug,
        requester_id=transfer_user.id,
        to_owner_type=OwnerType.INDIVIDUAL.value,
        to_owner_id=target_user.id,
        reason="Handover"
    )
    assert success is True
    assert err is None

    req = test_db.query(EventTransferRequest).filter_by(event_id=test_event.id).first()
    assert req is not None
    assert req.status == TransferStatus.PENDING.value
    assert req.to_user_id == target_user.id
    assert req.from_user_id == transfer_user.id

def test_request_event_transfer_unauthorized(test_db, target_user, test_event):
    from app.events.permissions import _is_event_owner
    print("Is Event Owner:", _is_event_owner(target_user, test_event))
    print("Is Super Admin:", target_user.is_super_admin())
    
    success, err = EventService.request_event_transfer(
        event_slug=test_event.slug,
        requester_id=target_user.id,  # Target user trying to initiate transfer for an event they don't own
        to_owner_type=OwnerType.INDIVIDUAL.value,
        to_owner_id=target_user.id,
        reason="Hostile takeover"
    )
    assert success is False
    assert err == "Unauthorized to transfer event ownership"

def test_approve_event_transfer_success(test_db, transfer_user, target_user, target_org, test_event):
    # Request transfer to an organisation
    membership = OrganisationMember(user_id=target_user.id, organisation_id=target_org.id)
    role = OrgRole(name="org_admin", organisation_id=target_org.id, template_name="org_admin")
    test_db.add_all([membership, role])
    test_db.flush()
    test_db.add(OrgUserRole(organisation_member_id=membership.id, role_id=role.id))
    test_db.commit()
    EventService.request_event_transfer(
        event_slug=test_event.slug,
        requester_id=transfer_user.id,
        to_owner_type=OwnerType.ORGANIZATION.value,
        to_owner_id=target_org.id,
        reason="Corporate move"
    )
    req = test_db.query(EventTransferRequest).filter_by(event_id=test_event.id).first()
    
    success, err = EventService.approve_event_transfer(
        request_id=req.id,
        approver_id=target_user.id
    )
    assert success is True
    assert err is None

    # Check request status
    test_db.refresh(req)
    assert req.status == TransferStatus.APPROVED.value
    assert req.approved_by_id == target_user.id

    # Check event ownership changed
    test_db.refresh(test_event)
    assert test_event.current_owner_type == OwnerType.ORGANIZATION
    assert test_event.current_owner_id == target_org.id

    # Check audit log
    log = test_db.query(EventTransferLog).filter_by(event_id=test_event.id).first()
    assert log is not None
    assert log.from_owner_type == OwnerType.INDIVIDUAL
    assert log.from_owner_id == transfer_user.id
    assert log.to_owner_type == OwnerType.ORGANIZATION
    assert log.to_owner_id == target_org.id
    assert log.transferred_by_id == target_user.id


def test_unauthorized_transfer_approval_does_not_mutate(test_db, transfer_user, target_user, target_org, test_event):
    EventService.request_event_transfer(
        event_slug=test_event.slug,
        requester_id=transfer_user.id,
        to_owner_type=OwnerType.ORGANIZATION.value,
        to_owner_id=target_org.id,
        reason="Corporate move"
    )
    req = test_db.query(EventTransferRequest).filter_by(event_id=test_event.id).first()
    initial_owner_type = test_event.current_owner_type
    initial_owner_id = test_event.current_owner_id

    success, error = EventService.approve_event_transfer(req.id, target_user.id)

    assert success is False
    assert "authorized" in error
    test_db.refresh(req)
    test_db.refresh(test_event)
    assert req.status == TransferStatus.PENDING.value
    assert test_event.current_owner_type == initial_owner_type
    assert test_event.current_owner_id == initial_owner_id
    assert test_db.query(EventTransferLog).filter_by(event_id=test_event.id).count() == 0

def test_update_event_bypasses_ownership_change(test_db, transfer_user, target_user, test_event):
    """
    Ensure `update_event` payload cannot secretly alter `current_owner_id`.
    """
    initial_owner_id = test_event.current_owner_id
    success, err = EventService.update_event(
        event_id=test_event.slug,
        data={"name": "New Name", "current_owner_id": target_user.id},
        user_id=transfer_user.id
    )
    assert success is True
    
    test_db.refresh(test_event)
    assert test_event.name == "New Name"
    # Ownership should remain unchanged since update_event ignores it
    assert test_event.current_owner_id == initial_owner_id
