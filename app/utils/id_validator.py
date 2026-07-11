"""
ID Validation Utility
Ensures internal IDs are always integers (BIGINT)
"""

def assert_internal_id(value):
    """
    Validate that an ID is a proper internal BIGINT (int).
    Raises ValueError if validation fails.
    """
    if not isinstance(value, int):
        # Handle string representation of integers safely
        if isinstance(value, str) and value.isdigit():
            return int(value)
        raise ValueError(f"Expected BIGINT internal ID (int), got {type(value).__name__}: {value}")

    if value <= 0:
        raise ValueError(f"Internal BIGINT ID must be positive, got: {value}")

    return value
