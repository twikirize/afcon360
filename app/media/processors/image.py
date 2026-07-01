# app/media/processors/image.py

from PIL import Image, ImageSequence
import io, hashlib


class ImageProcessor:
    """
    Optimize images to WebP with responsive size variants.
    Africa-first: aggressive compression, small file sizes.
    Supports animated WebP/GIF.
    """

    SIZES = {
        'tiny':   (100, 100),
        'small':  (300, 225),
        'medium': (600, 450),
        'large':  (1024, 768),
        'original': None,
    }

    QUALITY = {
        'webp': 75,
        'jpeg': 82,
        'png':  85,
    }

    @classmethod
    def is_animated(cls, file_obj) -> bool:
        """Check if image is animated (GIF/WebP)."""
        try:
            file_obj.seek(0)
            img = Image.open(file_obj)

            # Check for GIF animation
            if getattr(img, 'is_animated', False):
                return True

            # Check for WebP animation (PIL doesn't always detect this)
            if img.format == 'WEBP':
                file_obj.seek(0)
                header = file_obj.read(12)
                file_obj.seek(0)
                # ANIM flag in WebP header
                if b'ANIM' in header:
                    return True

            return False
        except Exception:
            return False

    @classmethod
    def process(cls, file_obj, storage_key_prefix: str, backend) -> dict:
        """
        Generate all size variants in WebP.
        Returns dict of {size_name: url}.
        Handles both static and animated images.
        """
        file_obj.seek(0)
        img = Image.open(file_obj)
        is_animated = cls.is_animated(file_obj)

        urls = {}

        for size_name, dimensions in cls.SIZES.items():
            buffer = io.BytesIO()

            if is_animated and size_name != 'original':
                # For animated images, only resize original and tiny
                # Other sizes use the original (saves CPU)
                if size_name == 'tiny':
                    # Create thumbnail from first frame
                    frames = []
                    for i, frame in enumerate(ImageSequence.Iterator(img)):
                        if i >= 10:  # Limit frames for tiny
                            break
                        frame = frame.convert('RGBA')
                        frame.thumbnail((100, 100), Image.Resampling.LANCZOS)
                        frames.append(frame)

                    if frames:
                        frames[0].save(
                            buffer,
                            format='WEBP',
                            save_all=True,
                            append_images=frames[1:],
                            duration=100,
                            loop=0,
                            quality=cls.QUALITY['webp'],
                            method=6
                        )
                    else:
                        # Fallback to static
                        img.thumbnail((100, 100), Image.Resampling.LANCZOS)
                        img.save(buffer, format='WEBP', quality=cls.QUALITY['webp'], method=6)
                else:
                    # For other sizes, save original as-is
                    buffer = cls._save_animated(img, buffer, max_frames=30)
            else:
                # Static image processing
                variant = img.copy()
                if dimensions:
                    variant.thumbnail(dimensions, Image.Resampling.LANCZOS)

                if variant.mode in ('RGBA', 'LA', 'P'):
                    variant = variant.convert('RGBA')
                else:
                    variant = variant.convert('RGB')

                variant.save(buffer, format='WEBP', quality=cls.QUALITY['webp'], method=6)

            buffer.seek(0)
            key = f"{storage_key_prefix}_{size_name}.webp"
            url = backend.save(buffer, key, 'image/webp')
            urls[size_name] = url

        return urls

    @classmethod
    def _save_animated(cls, img, buffer, max_frames=30) -> io.BytesIO:
        """Save animated image with frame limit."""
        frames = []
        for i, frame in enumerate(ImageSequence.Iterator(img)):
            if i >= max_frames:
                break
            frame = frame.convert('RGBA')
            frames.append(frame)

        if frames:
            frames[0].save(
                buffer,
                format='WEBP',
                save_all=True,
                append_images=frames[1:],
                duration=getattr(img, 'info', {}).get('duration', 100),
                loop=getattr(img, 'info', {}).get('loop', 0),
                quality=cls.QUALITY['webp'],
                method=6
            )
        else:
            buffer = io.BytesIO()
            img.save(buffer, format='WEBP', quality=cls.QUALITY['webp'], method=6)

        return buffer

    @classmethod
    def compute_hash(cls, file_obj) -> str:
        """SHA-256 hash for deduplication check."""
        file_obj.seek(0)
        h = hashlib.sha256()
        while chunk := file_obj.read(8192):
            h.update(chunk)
        file_obj.seek(0)
        return h.hexdigest()
