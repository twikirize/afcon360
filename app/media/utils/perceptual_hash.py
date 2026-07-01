# app/media/utils/perceptual_hash.py
"""
Perceptual hashing for near-duplicate image detection.
Uses average hash (aHash) to detect similar images even after resizing/cropping.
Lightweight alternative to heavy ML-based duplicate detection.
"""

import io
from PIL import Image
import numpy as np


class PerceptualHasher:
    """
    Generate perceptual hashes for near-duplicate detection.
    Based on average hash (aHash) algorithm.
    """

    @classmethod
    def compute(cls, file_obj, hash_size=8) -> str:
        """
        Compute perceptual hash of an image.
        Returns 64-character hex string.
        """
        try:
            file_obj.seek(0)
            img = Image.open(file_obj)

            # Convert to grayscale and resize
            img = img.convert('L')
            img = img.resize((hash_size, hash_size), Image.Resampling.LANCZOS)

            # Convert to numpy array
            pixels = np.array(img)
            avg = pixels.mean()

            # Generate hash: 1 if pixel > avg, 0 otherwise
            diff = pixels > avg
            hash_bits = diff.flatten().astype(int)

            # Convert to hex string
            hex_str = ''.join(f'{b:01x}' for b in hash_bits)
            file_obj.seek(0)
            return hex_str

        except Exception as e:
            # If image processing fails, return None
            file_obj.seek(0)
            return None

    @classmethod
    def hamming_distance(cls, hash1: str, hash2: str) -> int:
        """
        Calculate Hamming distance between two hashes.
        Lower distance = more similar images.
        0 = identical, 8+ = different images.
        """
        if not hash1 or not hash2 or len(hash1) != len(hash2):
            return 999  # Max distance for invalid comparison

        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

    @classmethod
    def is_similar(cls, hash1: str, hash2: str, threshold: int = 6) -> bool:
        """
        Check if two images are perceptually similar.
        Default threshold: 6 bits out of 64 (93.75% similar).
        """
        return cls.hamming_distance(hash1, hash2) <= threshold

    @classmethod
    def find_near_duplicates(cls, target_hash: str, existing_hashes: list,
                              threshold: int = 6) -> list:
        """
        Find near-duplicates from a list of existing hashes.
        Returns list of (hash, distance) tuples.
        """
        results = []
        for existing_hash in existing_hashes:
            dist = cls.hamming_distance(target_hash, existing_hash)
            if dist <= threshold:
                results.append((existing_hash, dist))
        return sorted(results, key=lambda x: x[1])
