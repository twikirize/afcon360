"""
app/tasks/cleanup.py

Scheduled cleanup tasks for accommodation module.
- Release expired temporary holds
"""

import logging
from datetime import datetime, timezone, timedelta
from app.celery_app import celery_app
from app.accommodation.services.availability_service import AvailabilityService

logger = logging.getLogger(__name__)


@celery_app.task(name="accommodation.cleanup_expired_holds")
def cleanup_expired_holds(hold_minutes: int = 15) -> int:
    """
    Release temporary holds that have expired.

    Args:
        hold_minutes: Maximum age of holds before they're considered expired

    Returns:
        Number of expired holds released
    """
    try:
        count = AvailabilityService.release_expired_holds(hold_minutes=hold_minutes)
        if count > 0:
            logger.info(f"Cleanup task released {count} expired holds")
        return count
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}", exc_info=True)
        return 0
