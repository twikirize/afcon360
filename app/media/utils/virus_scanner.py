# app/media/utils/virus_scanner.py
"""
Virus/malware scanning for uploaded files.
Uses ClamAV when available, falls back to magic-byte signature checks.
"""

import os
import subprocess
import tempfile
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class VirusScanner:
    """
    Scan files for malware/viruses.
    Primary: ClamAV (clamdscan daemon)
    Fallback: Signature-based magic byte checks
    """

    # Known malicious patterns (basic signature check)
    MALICIOUS_SIGNATURES = [
        b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*',
        b'<script',
        b'<?php',
        b'<%eval',
        b'<%execute',
    ]

    @classmethod
    def is_clamav_available(cls) -> bool:
        """Check if ClamAV daemon is running."""
        try:
            result = subprocess.run(
                ['clamdscan', '--version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @classmethod
    def scan_with_clamav(cls, file_path: str) -> Tuple[bool, str]:
        """
        Scan file using ClamAV daemon.
        Returns (is_clean, threat_name).
        """
        try:
            result = subprocess.run(
                ['clamdscan', '--no-summary', file_path],
                capture_output=True,
                text=True,
                timeout=30
            )

            # ClamAV returns 0 for clean, 1 for infected
            if result.returncode == 0:
                return True, ""
            elif result.returncode == 1:
                # Parse threat name from output
                output = result.stdout or result.stderr
                if "FOUND" in output:
                    threat = output.split("FOUND")[0].strip().split("/")[-1]
                    return False, threat
                return False, "Unknown threat"
            else:
                logger.warning(f"ClamAV scan error: {result.stderr}")
                return True, ""  # Fail open on error

        except subprocess.TimeoutExpired:
            logger.error("ClamAV scan timed out")
            return True, ""  # Fail open on timeout
        except Exception as e:
            logger.error(f"ClamAV scan failed: {e}")
            return True, ""  # Fail open on error

    @classmethod
    def scan_with_signatures(cls, file_obj) -> Tuple[bool, str]:
        """
        Fallback: Check file against known malicious signatures.
        Returns (is_clean, threat_name).
        """
        try:
            file_obj.seek(0)
            content = file_obj.read(4096)  # Check first 4KB
            file_obj.seek(0)

            content_lower = content.lower()

            for sig in cls.MALICIOUS_SIGNATURES:
                if sig in content or sig.lower() in content_lower:
                    return False, f"Suspicious pattern detected: {sig[:20]}"

            return True, ""

        except Exception as e:
            logger.error(f"Signature scan failed: {e}")
            return True, ""  # Fail open on error

    @classmethod
    def scan(cls, file_obj, filename: str = "upload") -> Tuple[bool, str]:
        """
        Main scan entry point.
        Tries ClamAV first, falls back to signature check.
        Returns (is_clean, threat_name).
        """
        # Write to temp file for ClamAV
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
            file_obj.seek(0)
            tmp.write(file_obj.read())
            tmp_path = tmp.name

        try:
            file_obj.seek(0)

            # Try ClamAV first
            if cls.is_clamav_available():
                is_clean, threat = cls.scan_with_clamav(tmp_path)
                if not is_clean:
                    return False, threat
                return True, ""

            # Fallback to signature check
            return cls.scan_with_signatures(file_obj)

        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
