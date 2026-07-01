# app/media/validators.py

ALLOWED_MAGIC_BYTES = {
    'image/jpeg': [b'\xff\xd8\xff'],
    'image/png':  [b'\x89PNG'],
    'image/webp': [b'RIFF'],
    'image/heic': [b'\x00\x00\x00'],  # ftyp box — needs secondary check
    'image/heif': [b'\x00\x00\x00'],
    'application/pdf': [b'%PDF'],
}


class UploadValidator:

    @classmethod
    def validate(cls, file, module: str, config: dict) -> tuple:
        """
        Validates: MIME type, magic bytes, file size.
        Returns (is_valid, error_message).
        """
        # 1. Size check
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        max_size = config.get('max_size', 20 * 1024 * 1024)
        if size > max_size:
            return False, f"File too large. Max {max_size // (1024*1024)}MB allowed."

        # 2. MIME type check against module config
        allowed = config.get('allowed_types', [])
        if file.content_type not in allowed:
            return False, f"File type {file.content_type} not allowed for {module}."

        # 3. Magic bytes check (don't trust Content-Type header alone)
        header = file.read(12)
        file.seek(0)
        expected_magic = ALLOWED_MAGIC_BYTES.get(file.content_type, [])
        if expected_magic:
            if not any(header.startswith(magic) for magic in expected_magic):
                return False, "File content does not match declared type."

        return True, ""
