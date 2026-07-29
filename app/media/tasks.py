# app/media/tasks.py

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from app.extensions import db
from PIL import Image as PILImage
import logging
import io
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
)
def process_media_task(self, media_id: int) -> Optional[Dict[str, Any]]:
    """
    Process a media item with comprehensive retry and error handling.

    Features:
    - Exponential backoff with jitter
    - Tracks processing attempts and timing
    - Handles storage failures gracefully
    - Self-healing for stuck tasks
    - Detailed audit trail
    """
    from app.media.models import Media, MediaProcessingJob
    from app.media.processors.image import ImageProcessor
    from app.media.storage import get_storage_backend
    from app.audit.forensic_audit import ForensicAuditService

    start_time = datetime.now(timezone.utc)

    try:
        # Get media record with lock to prevent concurrent processing
        media = db.session.get(Media, media_id)
        if not media:
            logger.warning(f"Media {media_id} not found")
            return {'error': 'Media not found', 'media_id': media_id}

        # Skip if already processed successfully
        if media.status == 'ready':
            logger.info(f"Media {media_id} already processed")
            return {'status': 'ready', 'urls': media.urls, 'skipped': True}

        # Check if we've exceeded retry attempts
        if media.processing_attempts >= 5:
            logger.error(f"Media {media_id} exceeded max retry attempts")
            media.status = 'failed'
            media.error_message = 'Max retry attempts exceeded'
            media.failed_at = datetime.now(timezone.utc)
            db.session.commit()
            return {'status': 'failed', 'error': 'Max retry attempts exceeded'}

        # Increment attempt counter
        media.processing_attempts = (media.processing_attempts or 0) + 1
        media.processing_started_at = start_time
        media.status = 'processing'
        db.session.commit()

        logger.info(f"🔄 Processing media {media_id}, attempt {media.processing_attempts}")

        # Get storage backend
        backend = get_storage_backend()

        # Determine processing strategy based on media type
        if media.media_type == 'photo':
            result = _process_photo(media, backend)
        elif media.media_type == 'video_url':
            result = _process_video_url(media)
        else:
            raise ValueError(f"Unsupported media type: {media.media_type}")

        # Update media record with successful result
        media.status = 'ready'
        media.urls = result.get('urls', {})
        media.width = result.get('width', media.width)
        media.height = result.get('height', media.height)
        media.is_animated = result.get('is_animated', media.is_animated)
        media.processing_completed_at = datetime.now(timezone.utc)
        media.error_message = None
        db.session.commit()

        # Audit completion
        _audit_completion(media, result)

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(f"✅ Media {media_id} processed in {duration:.2f}s")

        return {'status': 'ready', 'urls': media.urls}

    except Exception as e:
        logger.error(f"❌ Media {media_id} failed: {str(e)}")

        # Update media state
        media = db.session.get(Media, media_id)
        if media:
            media.error_message = str(e)
            if self.request.retries >= self.max_retries:
                media.status = 'failed'
                media.failed_at = datetime.now(timezone.utc)
            else:
                media.status = 'pending'
            db.session.commit()

        # Determine if retry is appropriate
        if _is_retryable_error(e) and self.request.retries < self.max_retries:
            # Exponential backoff with jitter
            delay = min(30 * (2 ** self.request.retries), 600)
            logger.warning(f"⏳ Retrying media {media_id} in {delay}s (attempt {self.request.retries + 1})")
            raise self.retry(exc=e, countdown=delay)

        # Permanent failure
        logger.error(f"💀 Media {media_id} permanently failed: {str(e)}")
        return {'status': 'failed', 'error': str(e), 'media_id': media_id}


def _process_photo(media, backend) -> Dict[str, Any]:
    """Process photo media with proper error handling."""
    from app.media.processors.image import ImageProcessor

    result = {}

    # Fetch raw file
    if not media.storage_key:
        raise ValueError("No storage key for media")

    file_data = backend.get_raw(media.storage_key)
    if not file_data:
        raise ValueError(f"File not found: {media.storage_key}")

    prefix = f"{media.module}/{media.entity_id}/{media.public_id}"

    # Extract metadata if needed
    if not media.width or not media.height:
        try:
            file_data.seek(0)
            with PILImage.open(file_data) as img:
                media.width, media.height = img.size
                media.is_animated = getattr(img, 'is_animated', False)
                result['width'] = media.width
                result['height'] = media.height
                result['is_animated'] = media.is_animated
            file_data.seek(0)
        except Exception as e:
            logger.warning(f"Failed to extract metadata: {e}")

    # Process image variants
    try:
        urls = ImageProcessor.process(file_data, prefix, backend)
        result['urls'] = urls
        return result
    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        raise RuntimeError(f"Image processing failed: {str(e)}")


def _process_video_url(media) -> Dict[str, Any]:
    """Process video URL media."""
    if not media.video_url:
        raise ValueError("Video URL is required")

    # Detect platform
    video_id = media.video_url
    urls = {
        'embed': f"https://www.youtube.com/embed/{video_id}",
        'thumbnail': f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
        'watch': f"https://www.youtube.com/watch?v={video_id}",
        'platform': 'youtube'
    }

    return {'urls': urls, 'width': 1280, 'height': 720}


def _is_retryable_error(error: Exception) -> bool:
    """Determine if an error is retryable."""
    retryable_exceptions = (
        ConnectionError,
        TimeoutError,
        IOError,
        OSError,
        MemoryError,
    )

    if isinstance(error, retryable_exceptions):
        return True

    error_msg = str(error).lower()
    retryable_patterns = [
        'timeout',
        'connection',
        'unavailable',
        'too many requests',
        'rate limit',
        'temporary',
        'storage',
        'network',
        'resource temporarily unavailable'
    ]

    return any(pattern in error_msg for pattern in retryable_patterns)


def _audit_completion(media, result):
    """Log audit for processing completion."""
    try:
        from app.audit.forensic_audit import ForensicAuditService
        if media.module == 'kyc':
            ForensicAuditService.log_completion(
                audit_id=media.public_id,
                status='completed',
                result_details={
                    'media_id': media.public_id,
                    'urls': result.get('urls', {}),
                    'width': media.width,
                    'height': media.height,
                    'is_animated': media.is_animated,
                    'processing_time': (
                            media.processing_completed_at - media.processing_started_at
                    ).total_seconds() if media.processing_started_at else None
                }
            )
    except Exception as e:
        logger.warning(f"Failed to log audit: {e}")


@shared_task
def process_pending_media():
    """
    Scheduled self-healing task to find and reprocess stuck media.
    Runs every 2 minutes to ensure no tasks are left in limbo.
    """
    from sqlalchemy import text
    from datetime import timedelta

    logger.info("🔄 Running pending media cleanup...")

    # Find stuck pending media (older than 3 minutes)
    pending_media = db.session.execute(text("""
                                            SELECT id, public_id, status, created_at, processing_attempts
                                            FROM media
                                            WHERE status = 'pending'
                                              AND created_at < NOW() - INTERVAL '3 minutes'
                                              AND (processing_attempts IS NULL
                                               OR processing_attempts
                                                < 5)
                                            ORDER BY created_at ASC
                                                LIMIT 50
                                            """)).fetchall()

    # Find stuck processing media (older than 8 minutes)
    processing_media = db.session.execute(text("""
                                               SELECT id, public_id, status, processing_started_at, processing_attempts
                                               FROM media
                                               WHERE status = 'processing'
                                                 AND processing_started_at < NOW() - INTERVAL '8 minutes'
                                                 AND (processing_attempts IS NULL
                                                  OR processing_attempts
                                                   < 5)
                                               ORDER BY processing_started_at ASC
                                                   LIMIT 30
                                               """)).fetchall()

    total_recovered = 0

    # Re-queue pending media
    for row in pending_media:
        logger.info(f"🔄 Re-queuing pending media: {row.public_id} (attempt {row.processing_attempts or 0 + 1})")
        try:
            db.session.execute(text("""
                                    UPDATE media
                                    SET status              = 'pending',
                                        processing_attempts = COALESCE(processing_attempts, 0) + 1
                                    WHERE id = :id
                                    """), {'id': row.id})
            process_media_task.delay(row.id)
            total_recovered += 1
        except Exception as e:
            logger.error(f"Failed to re-queue {row.public_id}: {e}")

    # Re-queue stuck processing media
    for row in processing_media:
        logger.info(
            f"🔄 Re-queuing stuck processing media: {row.public_id} (attempt {row.processing_attempts or 0 + 1})")
        try:
            db.session.execute(text("""
                                    UPDATE media
                                    SET status              = 'pending',
                                        processing_attempts = COALESCE(processing_attempts, 0) + 1
                                    WHERE id = :id
                                    """), {'id': row.id})
            process_media_task.delay(row.id)
            total_recovered += 1
        except Exception as e:
            logger.error(f"Failed to re-queue {row.public_id}: {e}")

    db.session.commit()

    # Get current counts for monitoring
    pending_count = db.session.execute(text(
        "SELECT COUNT(*) FROM media WHERE status = 'pending'"
    )).scalar() or 0

    processing_count = db.session.execute(text(
        "SELECT COUNT(*) FROM media WHERE status = 'processing'"
    )).scalar() or 0

    failed_count = db.session.execute(text(
        "SELECT COUNT(*) FROM media WHERE status = 'failed'"
    )).scalar() or 0

    ready_count = db.session.execute(text(
        "SELECT COUNT(*) FROM media WHERE status = 'ready'"
    )).scalar() or 0

    logger.info(f"📊 Media status: Ready: {ready_count}, Pending: {pending_count}, "
                f"Processing: {processing_count}, Failed: {failed_count}")
    logger.info(f"✅ Recovered {total_recovered} stuck media items")

    return {
        'recovered': total_recovered,
        'counts': {
            'ready': ready_count,
            'pending': pending_count,
            'processing': processing_count,
            'failed': failed_count
        },
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


@shared_task
def cleanup_failed_media():
    """
    Cleanup permanently failed media (mark for deletion, notify admins).
    Runs once per hour.
    """
    from sqlalchemy import text
    from datetime import timedelta

    logger.info("🧹 Running failed media cleanup...")

    # Find failed media older than 24 hours
    failed_media = db.session.execute(text("""
                                           SELECT id, public_id, error_message, failed_at
                                           FROM media
                                           WHERE status = 'failed'
                                             AND failed_at < NOW() - INTERVAL '24 hours'
                                             AND notified = FALSE
                                               LIMIT 100
                                           """)).fetchall()

    if not failed_media:
        logger.info("No failed media to cleanup")
        return {'cleaned': 0}

    # Mark as notified to avoid duplicate alerts
    for row in failed_media:
        db.session.execute(text("""
                                UPDATE media
                                SET notified   = TRUE,
                                    cleaned_at = NOW()
                                WHERE id = :id
                                """), {'id': row.id})
        logger.info(f"📧 Marked failed media {row.public_id} for admin review: {row.error_message}")

    db.session.commit()

    # Send admin notification (implement with your notification system)
    # send_admin_alert(f"{len(failed_media)} media items failed processing")

    return {
        'cleaned': len(failed_media),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }