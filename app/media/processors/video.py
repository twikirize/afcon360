# app/media/processors/video.py

import re


class YouTubeURLValidator:
    """
    Validates and extracts YouTube video IDs.
    No video storage — YouTube is the CDN.
    """

    PATTERNS = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})',
    ]

    @classmethod
    def extract_video_id(cls, url: str) -> str | None:
        """Extract YouTube video ID from URL. Returns None if invalid."""
        for pattern in cls.PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
