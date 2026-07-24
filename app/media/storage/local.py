# app/media/storage/local.py

import os
import shutil
from pathlib import Path

from app.media.storage import StorageBackend


class LocalStorageBackend(StorageBackend):
    """
    Filesystem storage for local development.
    Serves files via /media/files/ Flask route.
    """

    def _get_base_path(self):
        from flask import current_app
        path = current_app.config.get('MEDIA_LOCAL_PATH', '/tmp/afcon360_media')
        Path(path).mkdir(parents=True, exist_ok=True)
        return path

    def save(self, file_obj, storage_key: str, content_type: str) -> str:
        base = self._get_base_path()
        full_path = os.path.join(base, storage_key)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'wb') as f:
            shutil.copyfileobj(file_obj, f)
        from flask import current_app
        prefix = current_app.config.get('MEDIA_LOCAL_URL_PREFIX', '/media/files')
        return f"{prefix}/{storage_key}"

    def delete(self, storage_key: str) -> bool:
        full_path = os.path.join(self._get_base_path(), storage_key)
        if os.path.exists(full_path):
            os.remove(full_path)
        return True

    def get_url(self, storage_key: str, expires_in: int = None) -> str:
        # Local dev: signed URL concept doesn't apply, just return path
        from flask import current_app
        prefix = current_app.config.get('MEDIA_LOCAL_URL_PREFIX', '/media/files')
        return f"{prefix}/{storage_key}"

    def exists(self, storage_key: str) -> bool:
        return os.path.exists(os.path.join(self._get_base_path(), storage_key))

    def get_raw(self, storage_key: str):
        full_path = os.path.join(self._get_base_path(), storage_key)
        return open(full_path, 'rb')
