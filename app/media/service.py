# app/media/service.py

import uuid as uuid_lib
from app.extensions import db
from app.audit.forensic_audit import ForensicAuditService
from flask import current_app
from app.media.utils.perceptual_hash import PerceptualHasher
from app.media.utils.virus_scanner import VirusScanner
from app.media.utils.content_moderator import ContentModerator
from app.media.utils.quota_manager import QuotaManager
from app.media.settings_service import MediaSettingsService


class MediaService:
    PLACEHOLDER_IMAGE = '/static/images/no-image.png'

    @classmethod
    def get_display_url(cls, media):
        """Return media URL or placeholder if none exists."""
        if media and getattr(media, 'urls', None) and media.urls.get('original'):
            return media.urls['original']
        return cls.PLACEHOLDER_IMAGE

    @classmethod
    def _get_module_config(cls, module: str) -> dict:
        """
        Get module config with DB settings override.
        DB settings take precedence over config.py defaults.
        """
        # Start with config.py defaults
        config = current_app.config['MEDIA_MODULE_CONFIG'].get(module)
        if not config:
            raise ValueError(f"Unknown module: {module}")

        # Apply DB settings override
        db_settings = MediaSettingsService.get_effective_config()
        if db_settings:
            # Override security settings from DB
            config = config.copy()
            if 'virus_scan_enabled' in db_settings:
                config['virus_scan_enabled'] = db_settings['virus_scan_enabled']
            if 'content_moderation_enabled' in db_settings:
                config['content_moderation_enabled'] = db_settings['content_moderation_enabled']
            if 'perceptual_hash_enabled' in db_settings:
                config['perceptual_hash_enabled'] = db_settings['perceptual_hash_enabled']
            if 'perceptual_hash_threshold' in db_settings:
                config['perceptual_hash_threshold'] = db_settings['perceptual_hash_threshold']
            if 'webp_quality' in db_settings:
                config['webp_quality'] = db_settings['webp_quality']
            if 'avif_quality' in db_settings:
                config['avif_quality'] = db_settings['avif_quality']
            if 'jpeg_quality' in db_settings:
                config['jpeg_quality'] = db_settings['jpeg_quality']

        return config

    @classmethod
    def upload_photo(cls, file, module: str, entity_id: str,
                     uploader_user_id: int, caption: str = None,
                     is_cover: bool = False, upload_session_id: str = None) -> dict:
        """
        Upload a photo for any module.
        entity_id MUST be a public UUID string (not BIGINT).
        uploader_user_id is the internal BIGINT (for DB FK only).
        Returns: {'media_id': str, 'status': 'processing', 'poll_url': str}
        """
        from app.media.models import Media
        from app.media.validators import UploadValidator
        from app.media.processors.image import ImageProcessor
        from app.media.storage import get_storage_backend
        from app.media.tasks import process_media_task

        module_config = cls._get_module_config(module)

        # 1. Validate file
        is_valid, error = UploadValidator.validate(file, module, module_config)
        if not is_valid:
            raise ValueError(error)

        # 2. Check quota
        file_size = file.content_length or 0
        QuotaManager.enforce_quota(uploader_user_id, file_size, module)

        # 3. Virus scan
        is_clean, threat = VirusScanner.scan(file, file.filename or "upload")
        if not is_clean:
            raise ValueError(f"File rejected: security scan detected {threat}")

        # 4. Content moderation
        is_safe, reason = ContentModerator.moderate(file)
        if not is_safe:
            raise ValueError(f"File rejected: {reason}")

        # 5. Compute hashes
        sha256 = ImageProcessor.compute_hash(file)
        perceptual_hash = PerceptualHasher.compute(file)

        # 6. Check for exact duplicates (SHA-256)
        existing = db.session.query(Media).filter(
            Media.sha256_hash == sha256,
            Media.module == module,
            Media.is_deleted == False
        ).first()
        if existing:
            return {
                'media_id': existing.public_id,
                'status': existing.status,
                'urls': existing.urls,
                'deduplicated': True
            }

        # 7. Check for near-duplicates (perceptual hash)
        if perceptual_hash:
            near_dupes = PerceptualHasher.find_near_duplicates(
                perceptual_hash,
                [m.perceptual_hash for m in
                 db.session.query(Media).filter(
                     Media.module == module,
                     Media.is_deleted == False,
                     Media.perceptual_hash != None
                 ).all() if m.perceptual_hash]
            )
            if near_dupes:
                # Log but don't reject — user may want to upload similar image
                current_app.logger.info(
                    f"Near-duplicate detected for user {uploader_user_id}: "
                    f"distance={near_dupes[0][1]}"
                )

        # 8. Check if animated
        is_animated = ImageProcessor.is_animated(file)

        # 9. Get image dimensions
        width, height = None, None
        try:
            file.seek(0)
            from PIL import Image as PILImage
            img = PILImage.open(file)
            width, height = img.size
            file.seek(0)
        except Exception:
            pass

        # 10. Save raw file to storage
        backend = get_storage_backend()
        raw_key = f"{module}/{entity_id}/raw/{sha256[:16]}_{file.filename}"
        backend.save(file, raw_key, file.content_type)

        # 11. Create Media record
        public_id = str(uuid_lib.uuid4())
        media = Media(
            public_id=public_id,
            module=module,
            entity_id=entity_id,
            uploaded_by=uploader_user_id,
            media_type='photo',
            storage_key=raw_key,
            storage_backend=current_app.config.get('STORAGE_TYPE', 'local'),
            original_filename=file.filename,
            file_size=file_size,
            mime_type=file.content_type,
            width=width,
            height=height,
            is_animated=is_animated,
            sha256_hash=sha256,
            perceptual_hash=perceptual_hash,
            upload_session_id=upload_session_id,
            status='pending',
            caption=caption,
            is_cover=is_cover,
            is_public=module_config.get('is_public', True),
        )
        db.session.add(media)
        db.session.flush()

        # 12. Audit for KYC
        if module_config.get('audit_required'):
            ForensicAuditService.log_attempt(
                entity_type='media',
                entity_id=public_id,
                action='upload',
                user_id=uploader_user_id,
                details={
                    'module': module,
                    'entity_id': entity_id,
                    'filename': file.filename,
                    'size': file_size,
                    'sha256': sha256[:16]
                }
            )

        # 13. Queue async processing
        task = process_media_task.delay(media.id)
        db.session.commit()

        return {
            'media_id': public_id,
            'status': 'processing',
            'poll_url': f"/api/media/status/{public_id}",
            'celery_task_id': task.id,
            'quota_remaining': QuotaManager.get_quota_status(uploader_user_id, module)
        }

    @classmethod
    def submit_youtube_url(cls, youtube_url: str, module: str,
                           entity_id: str, uploader_user_id: int,
                           caption: str = None) -> dict:
        """
        Register a YouTube video URL (no file storage).
        """
        from app.media.models import Media
        from app.media.processors.video import YouTubeURLValidator

        video_id = YouTubeURLValidator.extract_video_id(youtube_url)
        if not video_id:
            raise ValueError("Invalid YouTube URL. Must be youtube.com or youtu.be link.")

        public_id = str(uuid_lib.uuid4())
        media = Media(
            public_id=public_id,
            module=module,
            entity_id=entity_id,
            uploaded_by=uploader_user_id,
            media_type='video_url',
            video_url=video_id,
            storage_backend='none',
            status='ready',
            caption=caption,
            is_public=True,
            urls={
                'embed': f"https://www.youtube.com/embed/{video_id}",
                'thumbnail': f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                'watch': f"https://www.youtube.com/watch?v={video_id}"
            }
        )
        db.session.add(media)
        db.session.commit()
        return {'media_id': public_id, 'status': 'ready', 'urls': media.urls}

    @classmethod
    def get_for_entity(cls, module: str, entity_id: str,
                       media_type: str = None) -> list:
        """Fetch all media for a module entity (e.g., all photos for a property)."""
        from app.media.models import Media
        q = db.session.query(Media).filter(
            Media.module == module,
            Media.entity_id == entity_id,
            Media.is_deleted == False
        ).order_by(Media.is_cover.desc(), Media.display_order.asc())
        if media_type:
            q = q.filter(Media.media_type == media_type)
        return q.all()

    @classmethod
    def delete(cls, media_public_id: str, requesting_user_id: int) -> bool:
        """Soft-delete a media record and remove from storage."""
        from app.media.models import Media
        from app.media.storage import get_storage_backend

        media = db.session.query(Media).filter(
            Media.public_id == media_public_id,
            Media.is_deleted == False
        ).first()
        if not media:
            return False

        # Delete from storage backend (best effort)
        if media.storage_key:
            try:
                get_storage_backend().delete(media.storage_key)
            except Exception:
                pass  # Log but don't fail

        media.soft_delete()  # BaseModel method
        db.session.commit()
        return True
