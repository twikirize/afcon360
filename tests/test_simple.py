"""Simple app test"""
def test_import():
    """Test that app can be imported"""
    try:
        from app import create_app
        assert create_app is not None
    except ImportError as e:
        assert False, f"Failed to import app: {e}"
