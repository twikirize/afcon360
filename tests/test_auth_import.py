from tests.db_connector import get_connection

def test_database_connection():
    """Test that we can connect to the database."""
    try:
        # Connect using our standardized connection helper
        conn = get_connection()
        cur = conn.cursor()

        # Test query
        cur.execute("SELECT current_user, current_database();")
        user, db = cur.fetchone()

        # Close cursor and connection
        cur.close()
        conn.close()

        # Assert that we got results
        assert user is not None
        assert db is not None

        # If we reach here, the test passes
        print("[OK] Connection successful!")
        print(f"Connected as user: {user}, Database: {db}")

    except Exception as e:
        # If any exception occurs, fail the test
        print("[ERROR] Error connecting to the database:", e)
        raise
