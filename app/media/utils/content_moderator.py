# app/media/utils/content_moderator.py
"""
Basic content moderation for uploaded images.
Uses lightweight heuristics and optional ML-based detection.
Designed to be extended with external APIs (AWS Rekognition, etc.)
"""

import io
import logging
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)


class ContentModerator:
    """
    Lightweight content moderation.
    Checks for:
    - Extreme aspect ratios (possible inappropriate content)
    - Very dark/bright images (possible malicious steganography)
    - Solid color images (spam/placeholder abuse)
    - Extremely large dimensions (potential DoS)
    """

    # Thresholds
    MAX_DIMENSION = 10000  # Reject images larger than this
    MIN_DIMENSION = 10     # Reject tiny images
    MAX_ASPECT_RATIO = 10  # Reject extreme aspect ratios
    MIN_AVG_BRIGHTNESS = 2  # Reject nearly black images
    MAX_AVG_BRIGHTNESS = 253  # Reject nearly white images
    MIN_COLOR_VARIANCE = 5  # Reject solid color images

    @classmethod
    def check_dimensions(cls, width: int, height: int) -> tuple:
        """Check for extreme dimensions (DoS prevention)."""
        if width > cls.MAX_DIMENSION or height > cls.MAX_DIMENSION:
            return False, f"Image dimensions too large: {width}x{height}"
        if width < cls.MIN_DIMENSION or height < cls.MIN_DIMENSION:
            return False, f"Image dimensions too small: {width}x{height}"
        return True, ""

    @classmethod
    def check_aspect_ratio(cls, width: int, height: int) -> tuple:
        """Check for extreme aspect ratios."""
        if width == 0 or height == 0:
            return False, "Invalid image dimensions"

        ratio = max(width, height) / min(width, height)
        if ratio > cls.MAX_ASPECT_RATIO:
            return False, f"Extreme aspect ratio: {ratio:.1f}:1"
        return True, ""

    @classmethod
    def check_brightness(cls, file_obj) -> tuple:
        """Check for extremely dark/bright images (possible steganography)."""
        try:
            file_obj.seek(0)
            img = Image.open(file_obj)
            img = img.convert('L')  # Grayscale
            img = img.resize((100, 100))  # Downsample for speed

            avg_brightness = np.array(img).mean()

            if avg_brightness < cls.MIN_AVG_BRIGHTNESS:
                return False, "Image too dark (possible steganography)"
            if avg_brightness > cls.MAX_AVG_BRIGHTNESS:
                return False, "Image too bright (possible spam)"

            return True, ""
        except Exception as e:
            logger.warning(f"Brightness check failed: {e}")
            return True, ""  # Fail open

    @classmethod
    def check_color_variance(cls, file_obj) -> tuple:
        """Check for solid color images (spam/placeholder abuse)."""
        try:
            file_obj.seek(0)
            img = Image.open(file_obj)
            img = img.convert('RGB')
            img = img.resize((50, 50))  # Downsample for speed

            pixels = np.array(img)
            variance = pixels.std(axis=(0, 1)).mean()

            if variance < cls.MIN_COLOR_VARIANCE:
                return False, "Image appears to be solid color (possible spam)"

            return True, ""
        except Exception as e:
            logger.warning(f"Color variance check failed: {e}")
            return True, ""  # Fail open

    @classmethod
    def moderate(cls, file_obj, width: int = None, height: int = None) -> tuple:
        """
        Run all moderation checks.
        Returns (is_safe, reason).
        """
        # Dimension checks
        if width and height:
            is_safe, reason = cls.check_dimensions(width, height)
            if not is_safe:
                return False, reason

            is_safe, reason = cls.check_aspect_ratio(width, height)
            if not is_safe:
                return False, reason

        # Image analysis checks
        is_safe, reason = cls.check_brightness(file_obj)
        if not is_safe:
            return False, reason

        is_safe, reason = cls.check_color_variance(file_obj)
        if not is_safe:
            return False, reason

        return True, ""
