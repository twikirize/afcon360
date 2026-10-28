"""
Read-only static audit for nullable pickup_time (Deploy 3 gate).
Walks app/, templates/, scripts/ and reports every pickup_time reference.
No DB. No writes. No app boot.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ("app", "templates", "scripts")
EXTS = {".py", ".html", ".js", ".sql", ".md"}
SELF = "scripts/audit_pickup_time_nullable.py"
PATTERN = re.compile(r"\bpickup_time\b")


def classify(rel: str, line: str) -> str:
    if rel.startswith("templates/"):
        return "template_null_safe" if ("|default" in line or " if " in line) else "template_risky"
    if rel.endswith(".py"):
        if "if " in line and "pickup_time" in line:
            return "py_null_guarded"
        if "if " in line and "None" in line:
            return "py_null_guarded"
        return "py_risky"
    return "other"


def main() -> int:
    hits = []
    for base in INCLUDE:
        for p in (ROOT / base).rglob("*"):
            if not p.is_file() or p.suffix.lower() not in EXTS:
                continue
            if p.relative_to(ROOT).as_posix() == SELF:
                continue
            if "__pycache__" in p.parts or "_retired_versions" in p.parts:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if PATTERN.search(line):
                    hits.append((p.relative_to(ROOT).as_posix(), i, line.strip()))
    buckets = {}
    for rel, _i, line in hits:
        b = classify(rel, line)
        buckets[b] = buckets.get(b, 0) + 1
    print(f"STATIC_HITS={len(hits)}")
    for b in sorted(buckets):
        print(f"  {b}={buckets[b]}")
    print()
    for rel, i, line in hits:
        print(f"{rel}:{i}: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())