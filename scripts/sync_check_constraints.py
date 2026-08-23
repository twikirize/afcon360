"""
AFCON360 CHECK Constraint Synchronizer

Purpose
-------
Detect CHECK-constraint drift between:

    SQLAlchemy models  -> desired state
    PostgreSQL DB      -> current state

and generate a normal Alembic migration that brings the DB toward the
model-defined desired state.

This exists because Alembic autogenerate does not reliably render
CreateCheckConstraintOp operations.

IMPORTANT
---------
The SQLAlchemy models are the source of truth.

The live database is inspected only to determine its current state.

Safe defaults:
    - missing model constraints are added
    - semantically different managed constraints are replaced
    - DB-only constraints are NOT dropped unless --prune-db is supplied
    - no migration is executed automatically

Examples
--------
Detect only:

    python scripts/sync_check_constraints.py --dry-run

Generate migration:

    python scripts/sync_check_constraints.py --accept-model-truth

Generate migration and explicitly prune DB-only managed constraints:

    python scripts/sync_check_constraints.py \
        --accept-model-truth \
        --prune-db

Add environment/message metadata:

    python scripts/sync_check_constraints.py \
        --environment development \
        --message "sync check constraints"

Debug:

    python scripts/sync_check_constraints.py --debug
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Dict, Tuple, List, Optional

from sqlalchemy import CheckConstraint, inspect


# ---------------------------------------------------------------------------
# Project bootstrap
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MANAGED_PREFIX = "ck_"

ConstraintKey = Tuple[str, str]


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Synchronize managed CHECK constraints from SQLAlchemy "
                    "models into the live PostgreSQL database."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect and report drift without creating a migration."
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show raw SQL and normalized SQL for differences."
    )

    parser.add_argument(
        "--prune-db",
        action="store_true",
        help=(
            "Allow dropping DB-only managed CHECK constraints that are not "
            "present in the SQLAlchemy models."
        ),
    )

    parser.add_argument(
        "--accept-model-truth",
        action="store_true",
        help=(
            "Explicitly confirm that SQLAlchemy models are authoritative "
            "and that reviewed model constraints may replace DB constraints. "
            "Required when generating a migration."
        ),
    )

    parser.add_argument(
        "--environment",
        default="development",
        help="Environment label recorded in the generated migration."
    )

    parser.add_argument(
        "--message",
        default="sync managed check constraints",
        help="Migration message."
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# SQL normalization
# ---------------------------------------------------------------------------

def normalize_sql(sql: Optional[str]) -> str:
    """
    Normalize PostgreSQL-reflected CHECK SQL for comparison.

    This function intentionally performs ONLY representation-level
    normalization.

    It must NOT remove information that could change the meaning of
    the constraint.
    """

    if not sql:
        return ""

    s = str(sql).strip().lower()

    # PostgreSQL frequently reflects:
    #
    #   column::text = ANY (
    #       ARRAY[
    #           'pending'::character varying,
    #           'sent'::character varying
    #       ]::text[]
    #   )
    #
    # as opposed to the model:
    #
    #   column IN ('pending', 'sent')
    #
    # First normalize ARRAY/ANY to IN. PostgreSQL commonly includes the
    # array suffix in the cast (`::text[]`), so handle that form explicitly.

    any_array_cast_pattern = re.compile(
        r"=\s*any\s*\(\s*array\s*\[(?P<values>.*?)\]\s*"
        r"::\s*[a-z_][a-z0-9_ ]*\[\]\s*\)",
        re.IGNORECASE | re.DOTALL,
    )

    s = any_array_cast_pattern.sub(
        lambda match: f" IN ({match.group('values')}) ",
        s,
    )

    any_array_pattern = re.compile(
        r"""
        =
        \s*
        any
        \s*
        \(
            \s*
            array
            \s*
            \[
                (?P<values>.*?)
            \]
            \s*
            (?:
                ::
                \s*
                [a-z_][a-z0-9_ ]*
                (?:\(\s*\d+(?:\s*,\s*\d+)?\s*\))?
            )?
            \s*
        \)
        """,
        re.IGNORECASE | re.VERBOSE | re.DOTALL,
    )

    def replace_any_array(match):
        values = match.group("values")
        return f" IN ({values}) "

    s = any_array_pattern.sub(replace_any_array, s)

    # Fallback for dialects that place additional cast text between the
    # closing ARRAY bracket and the ANY parenthesis.
    s = re.sub(
        r"(?P<column>[a-z_][a-z0-9_.]*)\s*=\s*any\s*\(\s*array\s*\["
        r"(?P<values>.*?)\]\s*(?:::[^)]*)?\)",
        lambda match: (
            f"{match.group('column')} IN ({match.group('values')})"
        ),
        s,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove PostgreSQL type casts.
    #
    # Examples:
    #   ::text
    #   ::character varying
    #   ::numeric
    #   ::numeric(10,2)
    #
    # IMPORTANT: the type-name body must NOT include spaces in its general
    # (single-word) form.  An earlier version used [a-z0-9_ ]* which greedily
    # consumed spaces, so a cast like ``0::numeric AND deposit_percentage``
    # matched ``numeric AND deposit_percentage`` (all letters/spaces) and was
    # stripped entirely — collapsing two distinct predicates into one and
    # producing false "semantic drift" on constraints that were actually
    # identical.  Multi-word type names (``character varying``,
    # ``double precision``, ``timestamp without time zone`` ...) are handled
    # by explicit alternatives so they still match without letting the
    # single-word branch eat across SQL keywords/identifiers.

    s = re.sub(
        r"""
        ::
        \s*
        (?:
            ".*?"
            |
            character[ ]varying
            |
            double[ ]precision
            |
            (?:timestamp|time)[ ](?:without|with)[ ]time[ ]zone
            |
            [a-z_][a-z0-9_]*
        )
        (?:\([ ]*\d+(?:[ ]*,[ ]*\d+)?[ ]*\))?
        """,
        "",
        s,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    # PostgreSQL may quote identifiers.
    s = s.replace('"', "")

    # Normalize whitespace.
    s = re.sub(r"\s+", " ", s).strip()

    # Normalize whitespace around punctuation/operators.
    s = re.sub(r"\s*,\s*", ",", s)
    s = re.sub(r"\s*<>\s*", "!=", s)
    s = re.sub(r"\s*>=\s*", ">=", s)
    s = re.sub(r"\s*<=\s*", "<=", s)
    s = re.sub(r"\s*!=\s*", "!=", s)
    s = re.sub(r"(?<![<>!=])\s*=\s*(?![=])", "=", s)
    s = re.sub(r"(?<![<>=!])\s*>\s*", ">", s)
    s = re.sub(r"(?<![<>=!])\s*<\s*", "<", s)

    # SQLAlchemy commonly renders ranges as BETWEEN while PostgreSQL
    # reflection returns the equivalent pair of comparisons.
    s = re.sub(
        r"\b([a-z_][a-z0-9_.]*)\s+between\s+([^\s]+)\s+and\s+([^\s)]+)",
        r"\1>=\2 and \1<=\3",
        s,
    )

    # Normalize IN syntax.  Case-insensitive because the ANY/ARRAY
    # rewrites above emit an upper-case " IN " token, while the model's
    # sqltext (already lower-cased at the top of this function) uses
    # lower-case "in".  Without IGNORECASE the DB side keeps "IN ("
    # and the model side becomes "in(", causing false semantic drift
    # on every constraint that PostgreSQL reflects via ANY(ARRAY[...]).
    s = re.sub(r"\bin\s*\(", "in(", s, flags=re.IGNORECASE)

    # Remove harmless outer whitespace around parentheses.
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)

    # Reflection may add parentheses around a single predicate.  Do not
    # remove parentheses belonging to IN lists or compound expressions.
    s = re.sub(
        r"(?<!in)\((?![^()]*\b(?:and|or)\b)([^(),]+(?:is not null|is null|!=|>=|<=|=|~|>|<)[^(),]*)\)",
        r"\1",
        s,
    )

    # Normalize boolean operators.
    s = re.sub(r"\band\b", " and ", s)
    s = re.sub(r"\bor\b", " or ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\bnot\s*\(", "not(", s)

    # Keep PostgreSQL-reflected and model-rendered quoted value lists in the
    # same shape.  Restrict this to quoted lists so SQL functions are not
    # mistaken for membership predicates.
    s = re.sub(
        r"\b([a-z_][a-z0-9_.]*)\s*(?:in\s*)?\((?P<values>'[^']*'(?:\s*,\s*'[^']*')+)\)",
        r"\1 in(\g<values>)",
        s,
    )

    return s.strip()


# ---------------------------------------------------------------------------
# Model inspection
# ---------------------------------------------------------------------------

def get_model_checks() -> Dict[ConstraintKey, str]:
    """
    Return CHECK constraints declared by SQLAlchemy models.

    The model is the desired state.
    """

    result: Dict[ConstraintKey, str] = {}

    for table in db.metadata.tables.values():

        for constraint in table.constraints:

            if not isinstance(constraint, CheckConstraint):
                continue

            if not constraint.name:
                continue

            if not constraint.name.startswith(MANAGED_PREFIX):
                continue

            result[(table.name, constraint.name)] = str(
                constraint.sqltext
            )

    return result


# ---------------------------------------------------------------------------
# Database inspection
# ---------------------------------------------------------------------------

def get_db_checks(engine) -> Dict[ConstraintKey, str]:
    """
    Return managed CHECK constraints currently present in PostgreSQL.
    """

    inspector = inspect(engine)

    result: Dict[ConstraintKey, str] = {}

    for table_name in inspector.get_table_names():

        for constraint in inspector.get_check_constraints(table_name):

            name = constraint.get("name")

            if not name:
                continue

            if not name.startswith(MANAGED_PREFIX):
                continue

            result[(table_name, name)] = constraint.get("sqltext", "")

    return result


# ---------------------------------------------------------------------------
# Drift classification
# ---------------------------------------------------------------------------

def diff(
    model_checks: Dict[ConstraintKey, str],
    db_checks: Dict[ConstraintKey, str],
):
    """
    Compare desired model state with current DB state.

    Returns:

        to_add
            Present in model, missing from DB.

        to_drop
            Present in DB, missing from model.

        to_replace
            Same constraint name exists in both but semantics differ.

        representation_matches
            Same semantics but different SQL representation.
    """

    to_add = []
    to_drop = []
    to_replace = []
    representation_matches = []

    for key, model_sql in model_checks.items():

        if key not in db_checks:
            to_add.append((key, model_sql))
            continue

        db_sql = db_checks[key]

        normalized_db = normalize_sql(db_sql)
        normalized_model = normalize_sql(model_sql)

        if normalized_db == normalized_model:
            if db_sql.strip() != model_sql.strip():
                representation_matches.append(
                    (key, db_sql, model_sql)
                )
        else:
            to_replace.append(
                (key, db_sql, model_sql)
            )

    for key, db_sql in db_checks.items():

        if key not in model_checks:
            to_drop.append((key, db_sql))

    return (
        to_add,
        to_drop,
        to_replace,
        representation_matches,
    )


# ---------------------------------------------------------------------------
# Alembic head
# ---------------------------------------------------------------------------

def get_current_head() -> str:
    """
    Resolve the current Alembic migration head from migrations/.
    """

    from alembic.script import ScriptDirectory

    migrations_dir = PROJECT_ROOT / "migrations"

    script = ScriptDirectory(str(migrations_dir))

    heads = script.get_heads()

    if not heads:
        raise RuntimeError(
            "No Alembic migration head found."
        )

    if len(heads) > 1:
        raise RuntimeError(
            "Multiple Alembic heads detected: "
            + ", ".join(heads)
            + ". Resolve the migration branches before syncing "
              "CHECK constraints."
        )

    return heads[0]


# ---------------------------------------------------------------------------
# Migration generation
# ---------------------------------------------------------------------------

def build_migration(
    to_add,
    to_drop,
    to_replace,
    down_revision: str,
    environment: str,
    message: str,
):
    """
    Build an executable Alembic migration.
    """

    upgrade_lines: List[str] = []
    downgrade_operations: List[List[str]] = []

    # ---------------------------------------------------------------
    # ADD
    # ---------------------------------------------------------------

    for (table, name), sql in to_add:

        upgrade_lines.append(
            f"    op.create_check_constraint("
            f"{name!r}, {table!r}, {sql!r}"
            f")"
        )

        downgrade_operations.append([
            f"    op.drop_constraint({name!r}, {table!r}, type_='check')"
        ])

    # ---------------------------------------------------------------
    # DROP
    # ---------------------------------------------------------------

    for (table, name), sql in to_drop:

        upgrade_lines.append(
            f"    op.drop_constraint("
            f"{name!r}, {table!r}, type_='check'"
            f")"
        )

        downgrade_operations.append([
            f"    op.create_check_constraint({name!r}, {table!r}, {sql!r})"
        ])

    # ---------------------------------------------------------------
    # REPLACE
    # ---------------------------------------------------------------

    for (table, name), old_sql, new_sql in to_replace:

        upgrade_lines.append(
            f"    op.drop_constraint("
            f"{name!r}, {table!r}, type_='check'"
            f")"
        )

        upgrade_lines.append(
            f"    op.create_check_constraint("
            f"{name!r}, {table!r}, {new_sql!r}"
            f")"
        )

        downgrade_operations.append([
            f"    op.drop_constraint({name!r}, {table!r}, type_='check')",
            f"    op.create_check_constraint({name!r}, {table!r}, {old_sql!r})",
        ])

    # Downgrade must undo changes in reverse order, preserving each
    # replacement's drop-then-create ordering.
    downgrade_lines = [
        line
        for operation in reversed(downgrade_operations)
        for line in operation
    ]

    if not upgrade_lines:
        return None

    revision_id = str(int(time.time()))

    timestamp = time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    upgrade_body = "\n".join(upgrade_lines)

    downgrade_body = "\n".join(downgrade_lines)

    return f'''"""
{message}

Generated by:
scripts/sync_check_constraints.py

Environment: {environment}

Revision ID: {revision_id}
Revises: {down_revision}
Create Date: {timestamp}

Source of truth:
    SQLAlchemy model metadata

Target:
    Live PostgreSQL database
"""

from alembic import op


revision = {revision_id!r}
down_revision = {down_revision!r}
branch_labels = None
depends_on = None


def upgrade():
{upgrade_body}


def downgrade():
{downgrade_body}
'''


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(
    to_add,
    to_drop,
    to_replace,
    representation_matches,
):
    print()
    print("=" * 72)
    print("AFCON360 CHECK CONSTRAINT DRIFT REPORT")
    print("=" * 72)

    print()
    print(f"Missing in DB / ADD       : {len(to_add)}")
    print(f"Semantic drift / REPLACE  : {len(to_replace)}")
    print(f"DB-only / ORPHANED        : {len(to_drop)}")
    print(
        f"Representation-only       : "
        f"{len(representation_matches)}"
    )

    if to_add:
        print()
        print("--- ADD ---")

        for key, _ in to_add:
            print(f"  + {key}")

    if to_replace:
        print()
        print("--- SEMANTIC DRIFT ---")

        for key, _, _ in to_replace:
            print(f"  ~ {key}")

    if to_drop:
        print()
        print("--- DB-ONLY / ORPHANED ---")

        for key, _ in to_drop:
            print(f"  - {key}")

    if representation_matches:
        print()
        print("--- REPRESENTATION DIFFERENCES ONLY ---")

        for key, _, _ in representation_matches:
            print(f"  = {key}")

    print()
    print("=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():

    args = parse_args()

    print()
    print("AFCON360 CHECK CONSTRAINT SYNCHRONIZER")
    print("-" * 72)
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Environment  : {args.environment}")
    print(f"Source       : SQLAlchemy models")
    print(f"Target       : Live PostgreSQL database")
    print()

    app = create_app()

    with app.app_context():

        engine = db.engine

        model_checks = get_model_checks()
        db_checks = get_db_checks(engine)

        (
            to_add,
            to_drop,
            to_replace,
            representation_matches,
        ) = diff(
            model_checks,
            db_checks,
        )

        print_report(
            to_add,
            to_drop,
            to_replace,
            representation_matches,
        )

        # -----------------------------------------------------------
        # Debug
        # -----------------------------------------------------------

        if args.debug:

            if to_replace:

                print()
                print("--- SEMANTIC DRIFT DETAILS ---")

                for key, db_sql, model_sql in to_replace:

                    print()
                    print(key)

                    print(
                        f"  DB raw         : {db_sql!r}"
                    )

                    print(
                        f"  Model raw      : {model_sql!r}"
                    )

                    print(
                        f"  DB normalized  : "
                        f"{normalize_sql(db_sql)!r}"
                    )

                    print(
                        f"  Model normalized: "
                        f"{normalize_sql(model_sql)!r}"
                    )

            if representation_matches:

                print()
                print("--- REPRESENTATION-ONLY DETAILS ---")

                for key, db_sql, model_sql in representation_matches:

                    print()
                    print(key)

                    print(
                        f"  DB raw         : {db_sql!r}"
                    )

                    print(
                        f"  Model raw      : {model_sql!r}"
                    )

                    print(
                        f"  DB normalized  : "
                        f"{normalize_sql(db_sql)!r}"
                    )

                    print(
                        f"  Model normalized: "
                        f"{normalize_sql(model_sql)!r}"
                    )

        # -----------------------------------------------------------
        # Nothing to change
        # -----------------------------------------------------------

        if not to_add and not to_replace:

            if to_drop and not args.prune_db:

                print()
                print(
                    "No model-to-DB drift requires migration."
                )

                print(
                    "DB-only managed constraints exist, but they "
                    "were NOT dropped."
                )

                print(
                    "Use --prune-db only after intentionally "
                    "confirming they should be removed."
                )

            else:

                print()
                print(
                    "No CHECK constraint migration required."
                )

            return

        # -----------------------------------------------------------
        # Protect against accidental DB cleanup
        # -----------------------------------------------------------

        migration_drops = to_drop if args.prune_db else []

        if to_drop and not args.prune_db:

            print()
            print(
                f"WARNING: {len(to_drop)} DB-only managed "
                "constraints will remain untouched."
            )

        # -----------------------------------------------------------
        # Dry run
        # -----------------------------------------------------------

        if args.dry_run:

            print()
            print(
                "DRY RUN: no migration file created."
            )

            return

        if not args.accept_model_truth:
            print()
            print(
                "SAFE STOP: migration generation is disabled unless you "
                "explicitly accept the SQLAlchemy models as the source of truth."
            )
            print()
            print(
                "Review the drift and database values first, then rerun with:"
            )
            print()
            print(
                "    python scripts/sync_check_constraints.py "
                "--accept-model-truth"
            )
            print()
            print(
                "This script never applies migrations; run flask db upgrade "
                "only after reviewing the generated file."
            )
            return

        # -----------------------------------------------------------
        # Resolve Alembic head
        # -----------------------------------------------------------

        down_revision = get_current_head()

        print()
        print(
            f"Alembic parent revision: {down_revision}"
        )

        # -----------------------------------------------------------
        # Build migration
        # -----------------------------------------------------------

        content = build_migration(
            to_add=to_add,
            to_drop=migration_drops,
            to_replace=to_replace,
            down_revision=down_revision,
            environment=args.environment,
            message=args.message,
        )

        if not content:
            print()
            print(
                "Nothing to migrate."
            )
            return

        # -----------------------------------------------------------
        # Write migration
        # -----------------------------------------------------------

        out_dir = (
            PROJECT_ROOT
            / "migrations"
            / "versions"
        )

        out_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        revision_id = str(int(time.time()))

        out_path = (
            out_dir
            / f"{revision_id}_sync_check_constraints.py"
        )

        out_path.write_text(
            content,
            encoding="utf-8",
        )

        print()
        print("=" * 72)
        print("MIGRATION CREATED")
        print("=" * 72)
        print()
        print(out_path)
        print()
        print(
            "Review the migration before upgrading."
        )
        print()
        print(
            "Then run:"
        )
        print()
        print(
            "    flask db upgrade"
        )
        print()
        print("=" * 72)


if __name__ == "__main__":
    main()