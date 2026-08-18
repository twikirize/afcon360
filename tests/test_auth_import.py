from sqlalchemy import func, select


def test_database_connection(db_session):
    """Verify PostgreSQL connectivity through SQLAlchemy expressions."""
    user, database = db_session.execute(
        select(func.current_user(), func.current_database())
    ).one()

    assert user
    assert database.endswith('_test')
