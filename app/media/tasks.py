# app/media/tasks.py

from celery import shared_task
from app.extensions import db
from PIL import Image as PILImage
import io


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_media_task(self, media_id: int):
    """
    Async media processing task.
    Runs image optimization after upload.
    Extracts dimensions and detects animation.
    """
    from app.media.models import Media, MediaProcessingJob
    from app.media.processors.image import ImageProcessor
    from app.media.storage import get_storage_backend

    try:
        media = db.session.get(Media, media_id)
        if not media:
            return {'error': 'Media not found'}

        media.status = 'processing'
        db.session.commit()

        backend = get_storage_backend()

        if media.media_type == 'photo':
            # Re-fetch raw file from storage
            raw_obj = backend.get_raw(media.storage_key)
            prefix = f"{media.module}/{media.entity_id}/{media.public_id}"

            # Extract dimensions if not already set
            if not media.width or not media.height:
                try:
                    raw_obj.seek(0)
                    img = PILImage.open(raw_obj)
                    media.width, media.height = img.size
                    media.is_animated = ImageProcessor.is_animated(raw_obj)
                    raw_obj.seek(0)
                except Exception:
                    pass

            urls = ImageProcessor.process(raw_obj, prefix, backend)

            media.urls = urls
            media.status = 'ready'

        elif media.media_type == 'video_url':
            # No processing needed — already stored as URL
            media.status = 'ready'
            media.urls = {
                'embed': f"https://www.youtube.com/embed/{media.video_url}",
                'thumbnail': f"https://img.youtube.com/vi/{media.video_url}/mqdefault.jpg",
                'watch': f"https://www.youtube.com/watch?v={media.video_url}"
            }

        db.session.commit()

        # Audit completion for KYC module
        if media.module == 'kyc':
            from app.audit.forensic_audit import ForensicAuditService
            ForensicAuditService.log_completion(
                audit_id=media.public_id,
                status='completed',
                result_details={
                    'media_id': media.public_id,
                    'urls': media.urls,
                    'width': media.width,
                    'height': media.height,
                    'is_animated': media.is_animated
                }
            )

        return {'status': 'ready', 'urls': media.urls}

    except Exception as exc:
        media = db.session.get(Media, media_id)
        if media:
            media.status = 'failed'
            media.error_message = str(exc)
            db.session.commit()
        raise self.retry(exc=exc)
