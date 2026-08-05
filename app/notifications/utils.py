"""
Notification Utilities (Rate limiting, Exponential Backoff, Idempotency)
"""

import math

def calculate_backoff(attempt: int, base_delay: int = 60) -> int:
    """Calculates exponential backoff delay in seconds."""
    return int(base_delay * math.pow(2, max(0, attempt - 1)))

def generate_idempotency_key(user_id: str, notification_type: str, timestamp: float) -> str:
    """Generates unique external_id for deduplication."""
    return f"notif_{notification_type}_{user_id}_{int(timestamp)}"
