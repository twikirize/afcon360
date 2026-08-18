from sqlalchemy import insert

from app.identity.models.user import User


def test_orm_insert_uses_migrated_postgresql_schema(db_session):
    """Exercise a SQLAlchemy insert through the shared PostgreSQL fixture."""
    statement = insert(User).values(
        username='sqlalchemy-test',
        email='sqlalchemy@test.com',
        password_hash='hash',
        email_verified=True,
        phone_verified=True,
    )
    result = db_session.execute(statement)
    assert result.inserted_primary_key[0] is not None
