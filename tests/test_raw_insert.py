from uuid import uuid4

from app.identity.models.user import User


def test_user_persistence_uses_orm(db_session):
    """Persist a user through the mapped model, never a handwritten INSERT."""
    user = User(
        public_id=str(uuid4()),
        username=f'raw-{uuid4().hex[:8]}',
        email=f'raw-{uuid4().hex[:8]}@test.example',
        password_hash='hash',
        is_verified=True,
        email_verified=True,
        phone_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    assert user.id is not None
