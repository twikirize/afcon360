#!/usr/bin/env python3
"""Read-only audit of the active Alembic revision graph.

This script reads migration source files only; it never imports or executes a
migration and never connects to a database. Pass --database-revision to check
whether an observed alembic_version belongs to the tracked active graph.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DIR = ROOT / "migrations" / "versions"
RETIRED_DIR = ROOT / "migrations" / "_retired_versions"

ASSIGNMENT = re.compile(r"(?m)^\s*(revision|down_revision)\s*=\s*(.*?)\s*(?:#.*)?$")


def _literal_assignments(source: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for match in ASSIGNMENT.finditer(source):
        name, rhs = match.group(1), match.group(2)
        try:
            values[name] = ast.literal_eval(rhs)
        except (ValueError, SyntaxError):
            # Dynamic revision identifiers cannot be safely inferred from text.
            values[name] = "__UNRESOLVED__"
    return values


def load_active_graph(root: Path = ROOT) -> tuple[dict[str, dict[str, Any]], list[str]]:
    active_dir = root / "migrations" / "versions"
    graph: dict[str, dict[str, Any]] = {}
    issues: list[str] = []

    for path in sorted(active_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        try:
            source = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            issues.append(f"cannot read {path.relative_to(root)}: {exc}")
            continue
        values = _literal_assignments(source)
        revision = values.get("revision")
        down_revision = values.get("down_revision", "__MISSING__")
        if not isinstance(revision, str) or not revision:
            issues.append(f"{path.relative_to(root)} has no literal revision assignment")
            continue
        if revision in graph:
            issues.append(
                f"duplicate active revision {revision!r}: "
                f"{graph[revision]['path']} and {path.relative_to(root)}"
            )
            continue
        if down_revision == "__UNRESOLVED__" or down_revision == "__MISSING__":
            issues.append(
                f"{path.relative_to(root)} has an unresolved down_revision assignment"
            )
            parents: tuple[str, ...] = ()
        elif down_revision is None:
            parents = ()
        elif isinstance(down_revision, str):
            parents = (down_revision,)
        elif isinstance(down_revision, (tuple, list)) and all(
            isinstance(item, str) for item in down_revision
        ):
            parents = tuple(down_revision)
        else:
            issues.append(
                f"{path.relative_to(root)} has unsupported down_revision value "
                f"{down_revision!r}"
            )
            parents = ()

        graph[revision] = {
            "revision": revision,
            "parents": parents,
            "path": str(path.relative_to(root)),
        }

    for revision, item in graph.items():
        for parent in item["parents"]:
            if parent not in graph:
                issues.append(
                    f"{item['path']} refers to missing active parent revision "
                    f"{parent!r}"
                )

    # A revision must not be its own ancestor. Detect ordinary cycles with DFS.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(revision: str) -> None:
        if revision in visiting:
            issues.append(f"cycle detected at revision {revision!r}")
            return
        if revision in visited:
            return
        visiting.add(revision)
        for parent in graph.get(revision, {}).get("parents", ()):
            if parent in graph:
                visit(parent)
        visiting.remove(revision)
        visited.add(revision)

    for revision in graph:
        visit(revision)

    return graph, issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-revision",
        help="revision value reported by a separately obtained alembic_version query",
    )
    args = parser.parse_args()

    graph, issues = load_active_graph()
    if not graph:
        print(f"ERROR: no active migration revisions found under {ACTIVE_DIR}")
        return 2

    children = {parent for item in graph.values() for parent in item["parents"]}
    roots = sorted(revision for revision, item in graph.items() if not item["parents"])
    heads = sorted(revision for revision in graph if revision not in children)

    print("Mode: source-only, read-only; migrations are not imported or executed.")
    print(f"Active migration directory: {ACTIVE_DIR}")
    print(f"Tracked active revisions: {len(graph)}")
    print("Roots (down_revision=None): " + (", ".join(roots) or "(none)"))
    print("Heads (no active children): " + (", ".join(heads) or "(none)"))
    print("Revision chain entries:")
    for revision, item in sorted(graph.items(), key=lambda pair: pair[1]["path"]):
        parent_text = ", ".join(item["parents"]) if item["parents"] else "None"
        print(f"  {revision} <- {parent_text}  [{item['path']}]")

    if len(roots) != 1:
        issues.append(f"expected one active root, found {len(roots)}")
    if len(heads) != 1:
        issues.append(f"expected one active head, found {len(heads)}")

    if args.database_revision:
        if args.database_revision not in graph:
            retired_match = False
            retired_path = RETIRED_DIR
            if retired_path.exists():
                for path in retired_path.glob("*.py"):
                    values = _literal_assignments(
                        path.read_text(encoding="utf-8-sig")
                    )
                    if values.get("revision") == args.database_revision:
                        retired_match = True
                        print(
                            f"Database revision {args.database_revision!r} is NOT in "
                            f"the active graph; a matching retired script exists at "
                            f"{path.relative_to(ROOT)}."
                        )
                        break
            if not retired_match:
                print(
                    f"Database revision {args.database_revision!r} is NOT in the "
                    "active graph and was not found in migrations/_retired_versions."
                )
            issues.append(
                f"database revision {args.database_revision!r} is not an active revision"
            )
        else:
            print(f"Database revision {args.database_revision!r} is present in the active graph.")

    if issues:
        print("RESULT: BLOCKED")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("RESULT: graph is structurally connected (this does not prove database parity).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
