"""Extract physical-schema evidence for manual inspection.

This script does NOT decide whether schemas are identical. It reports
ground-truth facts: file SHA-256, byte sizes, actual diff line counts, and
extracted object lists per category. It never claims "identical" without
showing the byte count and line count that prove it.

Run:
    python -m scripts.h3.extract_physical_evidence

Or with a custom directory:
    python scripts/h3/extract_physical_evidence.py --dir <path>
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import re
import sys
import tempfile
from pathlib import Path


DATABASES = ("reference", "prod", "test")
FILES = {
    "reference": "afcon360_h2p_replay_20261018_test_normalized.sql",
    "prod":      "afcon360_prod_normalized.sql",
    "test":      "afcon360_test_normalized.sql",
}

ENUM_RE       = re.compile(r'CREATE\s+TYPE\s+"public"\."([^"]+)"\s+AS\s+ENUM', re.IGNORECASE)
INDEX_AGENT_RE = re.compile(
    r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+"([^"]+)"\s+ON\s+"public"\."(agent_[^"]+)"',
    re.IGNORECASE,
)
FUNCTION_RE   = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+"([^"]+)"\."([^"]+)"', re.IGNORECASE)
TRIGGER_RE    = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+"([^"]+)"', re.IGNORECASE)
TABLE_AGENT_RE = re.compile(r'CREATE\s+TABLE\s+"public"\."(agent_[^"]+)"\s*\(([^;]*?)\)\s*;', re.IGNORECASE | re.DOTALL)
TIMESTAMP_COL_RE = re.compile(r'"([^"]+)"\s+(timestamp[^,\n]*)', re.IGNORECASE)
FK_RE         = re.compile(
    r'ADD\s+CONSTRAINT\s+"([^"]+)"\s+FOREIGN\s+KEY\s+\([^)]+\)\s+REFERENCES\s+"public"\."([^"]+)"\s*\([^)]*\)\s*([^;]*);',
    re.IGNORECASE,
)


def sha256_and_size(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
            total += len(chunk)
    return h.hexdigest(), total


def line_count(path: Path) -> int:
    with path.open("rb") as f:
        return sum(1 for _ in f)


def run_diff(a: Path, b: Path, out: Path) -> tuple[int, int]:
    """Produce a diff and return (size_in_bytes, line_count). Never claims 'empty' without proof."""
    a_lines = a.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    b_lines = b.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    diff = list(difflib.unified_diff(a_lines, b_lines, fromfile=a.name, tofile=b.name))
    out.write_text("".join(diff), encoding="utf-8")
    return out.stat().st_size, len(diff)


def write_list(path: Path, items: list[str]) -> None:
    path.write_text("\n".join(items) + ("\n" if items else ""), encoding="utf-8")


# --- extractors -----------------------------------------------------------------

def extract_enums(text: str) -> list[str]:
    return sorted(ENUM_RE.findall(text))


def extract_agent_indexes(text: str) -> list[str]:
    return sorted(f"{ix} ON {tbl}" for ix, tbl in INDEX_AGENT_RE.findall(text))


def extract_functions(text: str) -> list[str]:
    return sorted(f"{schema}.{name}" for schema, name in FUNCTION_RE.findall(text))


def extract_triggers(text: str) -> list[str]:
    return sorted(TRIGGER_RE.findall(text))


def extract_fk_actions(text: str) -> list[str]:
    results = []
    for name, target, tail in FK_RE.findall(text):
        tail = tail.strip()
        m = re.search(r'ON\s+DELETE\s+([A-Z ]+?)(?:\s+ON\s+UPDATE|$)', tail, re.IGNORECASE)
        action = m.group(1).strip().upper() if m else "NO ACTION"
        results.append(f"{name} -> {target} [ON DELETE {action}]")
    return sorted(results)


def extract_agent_timestamps(text: str) -> list[str]:
    results = []
    for table, body in TABLE_AGENT_RE.findall(text):
        for col, typ in TIMESTAMP_COL_RE.findall(body):
            results.append(f"{table}.{col} = {typ.strip()}")
    return sorted(results)


# --- main -----------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir",
        default=str(Path(tempfile.gettempdir()) / "afcon360_physical_schema_investigation"),
        help="Directory containing the normalized .sql dumps",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory (defaults to <dir>/manual_inspection)",
    )
    args = parser.parse_args(argv)

    src = Path(args.dir)
    if not src.is_dir():
        print(f"BLOCKED: investigation directory not found: {src}")
        print("Run the physical-schema investigation first, or pass --dir.")
        return 2

    out = Path(args.out) if args.out else src / "manual_inspection"
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("1. FILE IDENTITY (ground truth — these are the facts)")
    print("=" * 80)
    paths: dict[str, Path] = {}
    for db in DATABASES:
        p = src / FILES[db]
        if not p.is_file():
            print(f"  MISSING: {FILES[db]}")
            continue
        paths[db] = p
        sha, size = sha256_and_size(p)
        print(f"  {db:10}  bytes={size:>10,}  lines={line_count(p):>8,}  sha256={sha}")

    if len(paths) != 3:
        print("\nBLOCKED: not all three normalized dumps present.")
        return 2

    # --- 2. Diffs with explicit proof ---
    print()
    print("=" * 80)
    print("2. ACTUAL DIFFS (byte size + line count prove whether schemas match)")
    print("=" * 80)
    pairs = [("reference", "prod"), ("reference", "test"), ("prod", "test")]
    for a, b in pairs:
        out_path = out / f"diff_{a}_vs_{b}.txt"
        size, lines = run_diff(paths[a], paths[b], out_path)
        if size == 0 and lines == 0:
            verdict = "IDENTICAL   (0 bytes, 0 lines — proven)"
        else:
            verdict = f"DIFFERENT   ({lines:,} diff lines, {size:,} bytes)"
        print(f"  {a:10} vs {b:10}  ->  {verdict}   [{out_path.name}]")

    # --- 3. Per-category extracts ---
    print()
    print("=" * 80)
    print("3. PER-CATEGORY EXTRACTS (for manual inspection)")
    print("=" * 80)

    texts = {db: p.read_text(encoding="utf-8", errors="replace") for db, p in paths.items()}

    categories = {
        "enums":            extract_enums,
        "agent_indexes":    extract_agent_indexes,
        "functions":        extract_functions,
        "triggers":         extract_triggers,
        "fk_actions":       extract_fk_actions,
        "agent_timestamps": extract_agent_timestamps,
    }

    for cat, fn in categories.items():
        print(f"\n--- {cat} ---")
        per_db: dict[str, list[str]] = {db: fn(texts[db]) for db in DATABASES}
        print(f"  reference: {len(per_db['reference'])}")
        print(f"  prod:      {len(per_db['prod'])}")
        print(f"  test:      {len(per_db['test'])}")

        for db in DATABASES:
            write_list(out / f"{cat}_{db}.txt", per_db[db])

        for a, b in pairs:
            only_a = sorted(set(per_db[a]) - set(per_db[b]))
            only_b = sorted(set(per_db[b]) - set(per_db[a]))
            if only_a or only_b:
                print(f"  {a} vs {b}:  {len(only_a)} only in {a},  {len(only_b)} only in {b}")
                write_list(out / f"{cat}_{a}_only.txt", only_a)
                write_list(out / f"{cat}_{b}_only.txt", only_b)
            else:
                print(f"  {a} vs {b}:  identical lists")

    # --- 4. Manifest ---
    summary = out / "EVIDENCE_SUMMARY.txt"
    with summary.open("w", encoding="utf-8") as f:
        f.write(f"Physical schema evidence — extracted {len(list(out.glob('*.txt'))) - 1} files\n\n")
        f.write(f"Source dumps: {src}\n")
        f.write(f"Extracted to: {out}\n\n")
        f.write("Files present (open any of these for manual inspection):\n")
        for p in sorted(out.iterdir()):
            if p.is_file() and p.name != summary.name:
                f.write(f"  {p.name:55}  {p.stat().st_size:>10,} bytes\n")

    print()
    print("=" * 80)
    print(f"All extracted evidence saved to: {out}")
    print(f"Open this first:                {summary}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())