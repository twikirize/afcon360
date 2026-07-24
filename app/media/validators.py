# app/media/validators.py

# Magic-byte signatures used to *sniff* the real file type from its bytes,
# rather than trusting the client-declared Content-Type (which can be wrong
# when a file has a mismatched extension, e.g. a .png that is really WebP).
MAGIC_SIGNATURES = [
    (b'\xff\xd8\xff', 'image/jpeg'),
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'RIFF', 'image/webp'),          # WebP: RIFF<size>WEBP
    (b'%PDF', 'application/pdf'),
    (b'\x00\x00\x00\x00ftyp', 'image/heic'),   # HEIC ftyp box at offset 0
    (b'\x00\x00\x00\x18ftyp', 'image/heic'),   # HEIC (18 = box size)
    (b'\x00\x00\x00\x1cheic', 'image/heic'),
    (b'\x00\x00\x00\x20ftyp', 'image/heif'),
    (b'ftypheic', 'image/heic'),      # ftyp may appear after a 4-byte size
    (b'ftypmif1', 'image/heif'),
]


def sniff_type(header: bytes) -> str:
    """Return the media MIME type inferred from the file's leading bytes."""
    for magic, mime in MAGIC_SIGNATURES:
        if header.startswith(magic):
            return mime
    # HEIC/HEIF store the ftyp box after a 4-byte size; scan a wider window.
    if b'ftypheic' in header or b'ftypmif1' in header or b'ftypavif' in header:
        return 'image/heic'
    return ''


class UploadValidator:

    @classmethod
    def validate(cls, file, module: str, config: dict) -> tuple:
        """
        Validates: file size, real content type (sniffed from magic bytes),
        and module allow-list. Returns (is_valid, error_message).

        The real type is sniffed from the file bytes, not the client-declared
        Content-Type, so a .png file that is actually WebP is accepted as WebP
        (and vice versa) instead of being falsely rejected.
        """
        # 1. Size check
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        max_size = config.get('max_size', 20 * 1024 * 1024)
        if size > max_size:
            return False, f"File too large. Max {max_size // (1024*1024)}MB allowed."

        # 2. Sniff the REAL type from magic bytes
        header = file.read(32)
        file.seek(0)
        real_type = sniff_type(header)
        if not real_type:
            # Unrecognized signature — fall back to the declared type so we
            # don't hard-reject unknown-but-valid files.
            real_type = (file.content_type or '').split(';')[0].strip()

        # 3. Allow-list check (against the sniffed/real type)
        allowed = config.get('allowed_types', [])
        if real_type not in allowed:
            declared = (file.content_type or '').split(';')[0].strip()
            return False, (
                f"File type '{real_type or declared}' is not allowed for {module}."
            )

        return True, ""

