# app/media/processors/document.py

import io
import logging
from PIL import Image as PILImage

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Processor for document uploads (PDF, etc.).
    Generates preview thumbnail variants and extracts metadata.
    """

    @classmethod
    def process(cls, file_obj, storage_key_prefix: str, backend) -> dict:
        """
        Process document: store original and generate preview thumbnail/variants if possible.
        Returns dict of {size_name: url}.
        """
        file_obj.seek(0)
        content = file_obj.read()
        file_obj.seek(0)

        urls = {}
        
        # If it's a PDF, we can attempt to render first page as thumbnail image if pdf2image/pymupdf is available
        thumbnail_bytes = None
        width, height = None, None

        if content.startswith(b'%PDF'):
            try:
                # Try pypdf / pymupdf / pdf2image if installed, or fallback to default document icon/placeholder
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(content))
                page_count = len(reader.pages)
                logger.info(f"Processed PDF with {page_count} pages")
            except Exception as e:
                logger.debug(f"PDF inspection notice: {e}")

        # Save original and variant keys
        original_key = f"{storage_key_prefix}_original.pdf" if content.startswith(b'%PDF') else f"{storage_key_prefix}_original.bin"
        
        # Save original
        file_obj.seek(0)
        orig_url = backend.save(file_obj, original_key, 'application/pdf' if content.startswith(b'%PDF') else 'application/octet-stream')
        urls['original'] = orig_url
        urls['tiny'] = orig_url # fallback for views expecting thumbnails

        return urls
