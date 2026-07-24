# app/accommodation/services/media_service.py
"""
Accommodation Media Service - Official entry point for ALL accommodation media.

This is a thin wrapper around the unified media hub (app.media.service.MediaService).
Per project architecture, app/media is the SINGLE SOURCE OF TRUTH for uploads
(property photos, room photos, host media, etc.). Accommodation code MUST route
media through this service rather than storing files directly.

All uploads use module="accommodation" and entity_id=<property.public_id>
(the public UUID, never the internal BIGINT id).
"""

from typing import Dict, List, Optional
from app.media.service import MediaService


class AccommodationMediaService:
    """Delegates accommodation media operations to the unified media hub."""

    MODULE = "accommodation"

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    @staticmethod
    def upload_photo(
        file,
        entity_public_id: str,
        uploader_user_id: int,
        caption: str = None,
        is_cover: bool = False,
    ) -> Dict:
        """
        Upload a property/room photo to the unified media hub.

        entity_public_id: the property's public_id (UUID), NOT internal id.
        uploader_user_id: internal BIGINT of the uploading user (FK only).
        """
        return MediaService.upload_photo(
            file=file,
            module=AccommodationMediaService.MODULE,
            entity_id=entity_public_id,
            uploader_user_id=uploader_user_id,
            caption=caption,
            is_cover=is_cover,
        )

    @staticmethod
    def submit_youtube_url(
        youtube_url: str,
        entity_public_id: str,
        uploader_user_id: int,
        caption: str = None,
    ) -> Dict:
        """Register a YouTube tour/video URL for a property (no file storage)."""
        return MediaService.submit_youtube_url(
            youtube_url=youtube_url,
            module=AccommodationMediaService.MODULE,
            entity_id=entity_public_id,
            uploader_user_id=uploader_user_id,
            caption=caption,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    @staticmethod
    def get_property_media(property_public_id: str, media_type: str = None) -> List:
        """Get all media for a property from the unified hub."""
        return MediaService.get_for_entity(
            module=AccommodationMediaService.MODULE,
            entity_id=property_public_id,
            media_type=media_type,
        )

    @staticmethod
    def get_display_url(media) -> str:
        """Return a media URL or placeholder (delegates to MediaService)."""
        return MediaService.get_display_url(media)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    @staticmethod
    def delete(media_public_id: str, requesting_user_id: int) -> bool:
        """Soft-delete a media item via the unified hub."""
        return MediaService.delete(media_public_id, requesting_user_id)
