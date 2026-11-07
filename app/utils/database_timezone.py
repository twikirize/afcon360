"""Fail-closed PostgreSQL session timezone policy for AFCON360."""


def _require_utc_timezone(timezone_name, *, operation):
    actual = str(timezone_name or "").strip()
    if actual.upper() != "UTC":
        reported = actual if actual else "<empty>"
        raise RuntimeError(
            "AFCON360 requires PostgreSQL timezone UTC for "
            f"{operation}; PostgreSQL reported {reported!r}."
        )
    return "UTC"


def assert_postgresql_utc_session(connection, *, operation="database operation"):
    """Assert UTC without leaking an implicit SQLAlchemy transaction.

    If the caller already owns a transaction, the check runs inside it and
    leaves it alone. Otherwise, the read-only SHOW statement's implicit
    transaction is rolled back before returning. This is essential for
    Alembic: migration DDL must begin in its own real transaction so it commits.
    """
    had_transaction = connection.in_transaction()
    try:
        timezone_name = connection.exec_driver_sql("SHOW TimeZone").scalar_one()
        return _require_utc_timezone(timezone_name, operation=operation)
    finally:
        if not had_transaction and connection.in_transaction():
            connection.rollback()


def assert_postgresql_utc_dbapi_connection(
    dbapi_connection, *, operation="application database connection"
):
    """Assert UTC on a newly opened DBAPI connection without leaving a transaction."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SHOW TimeZone")
        row = cursor.fetchone()
        timezone_name = row[0] if row else None
    finally:
        try:
            cursor.close()
        finally:
            # The read opens an implicit transaction in psycopg2. Do not leave
            # that transaction open when SQLAlchemy takes ownership.
            dbapi_connection.rollback()
    return _require_utc_timezone(timezone_name, operation=operation)
