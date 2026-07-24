# app/media/storage/__init__.py
"""
Storage backend abstraction for media files.
Supports local filesystem (dev) and OCI Object Storage (production).
"""


class StorageBackend:
    """Abstract base — all backends implement this interface."""

    def save(self, file_obj, storage_key: str, content_type: str) -> str:
        """Save file. Returns public URL or storage path."""
        raise NotImplementedError

    def delete(self, storage_key: str) -> bool:
        raise NotImplementedError

    def get_url(self, storage_key: str, expires_in: int = None) -> str:
        """Get URL. expires_in=None for public URL, int for signed URL (seconds)."""
        raise NotImplementedError

    def exists(self, storage_key: str) -> bool:
        raise NotImplementedError

    def get_raw(self, storage_key: str):
        """Return file-like object for reading (used by image processor)."""
        raise NotImplementedError

    def create_presigned_upload(self, storage_key: str, content_type: str,
                                expires_in: int = 900):
        """
        Return a dict with a direct-to-storage upload target so the client can
        PUT/POST bytes straight to the bucket, bypassing the app server.

        Returns:
            {
                'url': str,            # direct upload URL
                'method': 'PUT'|'POST',
                'fields': dict,        # extra form fields (presigned POST)
                'headers': dict,       # required request headers (presigned PUT)
            }

        Backends without presigning support (e.g. local filesystem) raise
        NotImplementedError so callers fall back to server-streamed uploads.
        """
        raise NotImplementedError


def get_storage_backend() -> StorageBackend:
    """
    Factory — returns correct backend based on STORAGE_TYPE env var.
    Called once per request/task, not at import time.
    """
    from flask import current_app
    storage_type = current_app.config.get('STORAGE_TYPE', 'local')

    if storage_type == 'oci':
        from app.media.storage.oci import OCIStorageBackend
        return OCIStorageBackend()
    elif storage_type == 's3':
        from app.media.storage.s3 import S3StorageBackend
        return S3StorageBackend()
    else:
        from app.media.storage.local import LocalStorageBackend
        return LocalStorageBackend()
