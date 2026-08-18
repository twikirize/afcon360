from uuid import uuid4

from app.identity.models.user import User


def test_user_defaults_are_persisted_by_sqlalchemy(db_session):
    """Exercise mapped defaults against the migrated PostgreSQL schema."""
    user = User(
        public_id=str(uuid4()),
        username=f'raw-{uuid4().hex[:8]}',
        email=f'raw-{uuid4().hex[:8]}@test.example',
        password_hash='hash',
        is_verified=True,
        email_verified=True,
        phone_verified=True,
        is_active=True,
        kyc_level=2,
    )
    db_session.add(user)
    db_session.flush()
    assert db_session.get(User, user.id) is user
