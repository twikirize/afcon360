"""CLI safety tests for the retired ENUM conversion helper (no database access)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "migrate_enums_to_strings.py"


def test_execute_option_fails_before_generating_or_writing_sql(tmp_path: Path) -> None:
    output_path = tmp_path / "must_not_be_created.sql"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--execute",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert "--execute is intentionally unsupported" in result.stderr
    assert not output_path.exists()
