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


@celery_app.task(name="accommodation.cleanup_expired_holds", bind=True)
def cleanup_expired_holds(
    self,
    hold_minutes: int = 15,
    batch_size: int = 25,
) -> dict:
    """
    Release temporary holds that have expired.

    Args:
        hold_minutes: Maximum age of holds before they're considered expired

    Returns:
        Number of expired holds released in this page and continuation status.
    """
    batch_size = max(1, min(int(batch_size), 100))
    try:
        result = AvailabilityService.release_expired_holds(
            hold_minutes=hold_minutes,
            batch_size=batch_size,
        )
        if result["released"] > 0:
            logger.info(
                "Cleanup task released %s expired holds",
                result["released"],
            )

        continuation_queued = False
        if result["has_more"]:
            try:
                self.apply_async(
                    kwargs={
                        "hold_minutes": hold_minutes,
                        "batch_size": batch_size,
                    },
                    countdown=5,
                )
                continuation_queued = True
            except Exception:
                logger.exception("Could not schedule next accommodation hold-cleanup batch")

        return {
            **result,
            "continuation_queued": continuation_queued,
        }
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}", exc_info=True)
        return {"released": 0, "error": str(e), "continuation_queued": False}
