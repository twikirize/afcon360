#!/usr/bin/env python3
"""
Comprehensive Null Byte Scanner - Scans entire codebase for null bytes.
Generates detailed report with file locations, corruption severity, and recovery options.
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple, Dict
from collections import defaultdict

# Skip binary/media files
SKIP_DIRS = {
    '.git', '__pycache__', '.venv', 'venv', 'node_modules',
    '.pytest_cache', '.egg-info', '.idea', 'dist', 'build',
    '.vscode', '.env', 'htmlcov', '.coverage'
}

BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.tar', '.gz',
    '.pyc', '.so', '.db', '.sqlite', '.sqlite3', '.o', '.a', '.exe',
    '.dll', '.dylib', '.ico', '.wav', '.mp3', '.mp4', '.mov',
    '.pyd', '.lib', '.mo', '.npy', '.npz', '.pkl', '.obj', '.node',
    '.egg', '.cfg', '.fits', '.db-shm', '.db-wal', '.skill',
    '.idx', '.pack', '.rev', '.val'  # Added more binary extensions
}

CRITICAL_EXTENSIONS = {'.py', '.md', '.yml', '.yaml', '.json', '.html', '.js', '.ts'}


def should_skip_path(file_path: Path) -> bool:
    """Check if a file path should be skipped."""
    # Check if any skip directory is in the path
    for part in file_path.parts:
        if part in SKIP_DIRS:
            return True
    return False


def categorize_file(file_path: Path) -> str:
    """Categorize file by type."""
    suffix = file_path.suffix.lower()

    categories = {
        '.py': 'Python',
        '.md': 'Documentation',
        '.txt': 'Text',
        '.rst': 'ReStructuredText',
        '.html': 'HTML',
        '.htm': 'HTML',
        '.js': 'JavaScript',
        '.ts': 'TypeScript',
        '.tsx': 'TypeScript',
        '.jsx': 'JavaScript',
        '.css': 'CSS',
        '.scss': 'SCSS',
        '.sass': 'SASS',
        '.less': 'LESS',
        '.json': 'JSON',
        '.yaml': 'YAML',
        '.yml': 'YAML',
        '.toml': 'TOML',
        '.ini': 'INI',
        '.cfg': 'Config',
        '.conf': 'Config',
        '.sql': 'SQL',
        '.xml': 'XML',
        '.svg': 'SVG',
    }

    return categories.get(suffix, 'Other')


def scan_repository() -> Tuple[List[Tuple[str, int, str, str]], Dict]:
    """
    Scan entire repository for null bytes.
    Returns (corrupted_files, statistics).
    """
    corrupted = []
    stats = {
        'total_files': 0,
        'scanned_files': 0,
        'corrupted_files': 0,
        'total_null_bytes': 0,
        'by_type': defaultdict(int),
        'by_extension': defaultdict(int),
        'critical_corrupted': 0,
    }

    repo_root = Path(__file__).parent.parent

    for file_path in repo_root.rglob('*'):
        stats['total_files'] += 1

        # Skip directories entirely
        if file_path.is_dir():
            continue

        # Skip if path contains any skip directory
        if should_skip_path(file_path):
            continue

        # Skip binary files by extension
        if file_path.suffix.lower() in BINARY_EXTENSIONS:
            continue

        stats['scanned_files'] += 1

        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                null_count = content.count(b'\x00')

                if null_count > 0:
                    rel_path = str(file_path.relative_to(repo_root))
                    file_type = categorize_file(file_path)
                    severity = 'CRITICAL' if file_path.suffix.lower() in CRITICAL_EXTENSIONS else 'WARNING'

                    corrupted.append((rel_path, null_count, file_type, severity))

                    stats['corrupted_files'] += 1
                    stats['total_null_bytes'] += null_count
                    stats['by_type'][file_type] += 1
                    stats['by_extension'][file_path.suffix.lower()] += 1

                    if severity == 'CRITICAL':
                        stats['critical_corrupted'] += 1

        except (PermissionError, OSError):
            pass

    return sorted(corrupted, key=lambda x: x[1], reverse=True), stats


def print_report(corrupted: List[Tuple], stats: Dict):
    """Print comprehensive corruption report."""

    print(f"\n{'=' * 80}")
    print(f"COMPREHENSIVE NULL BYTE CORRUPTION REPORT")
    print(f"{'=' * 80}\n")

    # Summary Statistics
    print("📊 SCAN SUMMARY")
    print(f"{'─' * 80}")
    print(f"Total files in repo:          {stats['total_files']:,}")
    print(f"Files scanned:                {stats['scanned_files']:,}")
    print(f"Corrupted files found:        {stats['corrupted_files']:,}")
    print(f"Total null bytes:             {stats['total_null_bytes']:,}")
    print(f"🔴 CRITICAL files corrupted:   {stats['critical_corrupted']:,}")
    print(f"\n")

    if stats['corrupted_files'] == 0:
        print("✅ NO CORRUPTION FOUND! Repository is clean.\n")
        return

    # Breakdown by type
    print("📈 CORRUPTION BY FILE TYPE")
    print(f"{'─' * 80}")
    for file_type, count in sorted(stats['by_type'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {file_type:<20} {count:>3} file(s)")
    print(f"\n")

    # Breakdown by extension
    if stats['by_extension']:
        print("📝 CORRUPTION BY EXTENSION")
        print(f"{'─' * 80}")
        for ext, count in sorted(stats['by_extension'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {ext:<15} {count:>3} file(s)")
        print(f"\n")

    # Detailed file list (limit to first 50 for readability)
    print("📋 CORRUPTED FILES DETAIL (showing first 50)")
    print(f"{'─' * 80}")
    print(f"{'Severity':<10} {'Null Bytes':<12} {'Type':<15} {'Path':<43}")
    print(f"{'─' * 80}")

    display_count = min(50, len(corrupted))
    for file_path, null_count, file_type, severity in corrupted[:display_count]:
        severity_icon = "🔴" if severity == "CRITICAL" else "⚠️ "
        # Truncate path if too long
        display_path = file_path if len(file_path) <= 43 else "..." + file_path[-40:]
        print(f"{severity_icon:<10} {null_count:<12} {file_type:<15} {display_path:<43}")

    if len(corrupted) > 50:
        print(f"\n  ... and {len(corrupted) - 50} more files (see CORRUPTED_FILES.txt for full list)")

    print(f"\n")


def export_corrupted_list(corrupted: List[Tuple], repo_root: Path):
    """Export list of corrupted files for batch processing."""
    output_file = repo_root / 'CORRUPTED_FILES.txt'

    with open(output_file, 'w') as f:
        f.write("# Corrupted Files - Generated by Null Byte Scanner\n")
        f.write(f"# Total: {len(corrupted)} files\n\n")

        for file_path, null_count, file_type, severity in corrupted:
            f.write(f"{file_path} ({null_count} bytes, {severity})\n")

    print(f"✓ Corrupted files list exported to: {output_file}\n")


def main():
    """Main entry point."""
    repo_root = Path(__file__).parent.parent

    print(f"\n{'=' * 80}")
    print(f"🔍 SCANNING REPOSITORY FOR NULL BYTES...")
    print(f"{'=' * 80}\n")

    print(f"Repository root: {repo_root}")
    print(f"Scanning in progress...\n")

    # Run scan
    corrupted, stats = scan_repository()

    # Print report
    print_report(corrupted, stats)

    # Export file list if corrupted files found
    if corrupted:
        export_corrupted_list(corrupted, repo_root)

        print("🛠️  NEXT STEPS")
        print(f"{'─' * 80}")
        print("Option 1: Clean all corrupted files (removes null bytes only)")
        print("  $ python scripts/clean_null_bytes.py --fix\n")
        print("Option 2: Review specific file")
        print("  $ cat CORRUPTED_FILES.txt\n")
        print("Option 3: Restore from git history (if needed)")
        print("  $ git checkout <commit> -- <file_path>\n")
    else:
        print("✅ REPOSITORY IS CLEAN - No action needed!\n")


if __name__ == '__main__':
    sys.exit(main())