"""
Detects CHECK constraint drift between the models and the live database, and
writes a normal Alembic migration file for it.

Run any time, in any environment:
    flask db migrate ... is NOT used for this.
    python scripts/sync_check_constraints_ for_later.py

Safe by default: writes the file, does NOT run it.
Review the generated migration before `flask db upgrade`.

Why a standalone script and not an Alembic autogenerate hook?
------------------------------------------------------------
Alembic's autogenerate has TWO jobs: detect drift, and render the migration
file. It does the detection half for Unique/FK/Index constraints, but it
deliberately does NOT render CHECK-constraint *creates* (render.py raises
NotImplementedError for CreateCheckConstraintOp on purpose — that renderer was
never finished). So asking autogenerate to handle CHECK constraints fights the
tool. Here we do the detection ourselves in plain Python and we write the
migration file's text ourselves, using only fully-executable ops
(op.create_check_constraint / op.drop_constraint). That makes this portable:
no env.py edit, no comparator registration, and no dependency on Alembic
internals staying stable across versions.
"""

import re
import sys
import time
from pathlib import Path

from sqlalchemy import inspect, CheckConstraint

# When this file is executed directly, Python places ``scripts`` rather than
# the repository root at the front of sys.path. Add the root explicitly so
# the standalone utility can import the application package.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db


MANAGED_PREFIX = "ck_"


def normalize_sql(sql: str) -> str:
    """Normalize CHECK constraint SQL text for comparison.

    Handles: casts (::numeric), BETWEEN vs >=/<=, whitespace/paren spacing,
    and case. Lowercasing both sides also neutralizes harmless case drift
    (e.g. a constraint written 'PENDING' in the model but stored 'pending' in
    the DB) so it does not false-positive as drift.
    """
    s = sql.strip().lower()

    # Normalize "col = ANY (ARRAY['a'::type, 'b'::type])" -> "col IN ('a','b')"
    # This is Postgres's canonical reflected form for IN(...) checks and is
    # the single biggest source of false-positive "changed" diffs.
    s = re.sub(
        r"=\s*any\s*\(\s*array\s*\[(.*?)\]\s*(::\s*\"?[a-z_ ]+\"?(\(\s*\d+(\s*,\s*\d+)?\s*\))?)?\s*\)",
        r"in (\1)",
        s,
    )

    # Strip casts, including multi-word type names: "::character varying(255)",
    # "::numeric(10,2)", "::text", etc. Must run AFTER the ANY(ARRAY[...])
    # rewrite above since casts appear inside the array literal too.
    s = re.sub(r"::\s*\"?[a-z_ ]+\"?(\(\s*\d+(\s*,\s*\d+)?\s*\))?", "", s)

    # Normalize "col BETWEEN a AND b" -> "col >= a AND col <= b" so the model
    # and DB forms compare equal when they are semantically identical.
    s = re.sub(
        r"\(?\s*(\w+)\s+between\s+(.+?)\s+and\s+(.+?)\s*\)?",
        r"( \1 >= \2 and \1 <= \3 )",
        s,
    )

    # Drop quoting around identifiers/strings so 'pending' == "pending"
    s = s.replace('"', "")

    # Collapse parens/whitespace so "(x >= 0)" == "x >= 0"
    s = s.replace("(", " ").replace(")", " ")
    s = " ".join(s.split())

    # Tight comma spacing so "'a' , 'b'" == "'a','b'"
    s = re.sub(r"\s*,\s*", ",", s)

    return s


def get_model_checks():
    """Desired state, keyed by (table_name, constraint_name)."""
    result = {}
    for table in db.metadata.tables.values():
        for c in table.constraints:
            if (
                isinstance(c, CheckConstraint)
                and c.name
                and c.name.startswith(MANAGED_PREFIX)
            ):
                result[(table.name, c.name)] = str(c.sqltext)
    return result


def get_db_checks(engine):
    """Current state, keyed by (table_name, constraint_name)."""
    inspector = inspect(engine)
    result = {}
    for table_name in inspector.get_table_names():
        for c in inspector.get_check_constraints(table_name):
            name = c.get("name")
            if name and name.startswith(MANAGED_PREFIX):
                result[(table_name, name)] = c["sqltext"]
    return result


def diff(model_checks, db_checks):
    to_add, to_drop, to_replace = [], [], []

    for key, model_sql in model_checks.items():
        if key not in db_checks:
            to_add.append((key, model_sql))
        elif normalize_sql(db_checks[key]) != normalize_sql(model_sql):
            to_replace.append((key, db_checks[key], model_sql))

    for key, db_sql in db_checks.items():
        if key not in model_checks:
            to_drop.append((key, db_sql))

    return to_add, to_drop, to_replace


TEMPLATE = '''"""sync check constraints

Revision ID: {rev_id}
Revises: {down_revision}
Create Date: {create_date}
"""
from alembic import op

revision = "{rev_id}"
down_revision = "{down_revision}"
branch_labels = None
depends_on = None


def upgrade():
{upgrade_body}


def downgrade():
{downgrade_body}
'''


def build_migration(to_add, to_drop, to_replace, down_revision):
    up_lines, down_lines = [], []

    for (table, name), sql in to_add:
        up_lines.append(f'    op.create_check_constraint("{name}", "{table}", "{sql}")')
        down_lines.append(f'    op.drop_constraint("{name}", "{table}", type_="check")')

    for (table, name), sql in to_drop:
        up_lines.append(f'    op.drop_constraint("{name}", "{table}", type_="check")')
        down_lines.append(f'    op.create_check_constraint("{name}", "{table}", "{sql}")')

    for (table, name), old_sql, new_sql in to_replace:
        up_lines.append(f'    op.drop_constraint("{name}", "{table}", type_="check")')
        up_lines.append(f'    op.create_check_constraint("{name}", "{table}", "{new_sql}")')
        down_lines.append(f'    op.drop_constraint("{name}", "{table}", type_="check")')
        down_lines.append(f'    op.create_check_constraint("{name}", "{table}", "{old_sql}")')

    if not up_lines:
        return None

    down_lines.reverse()  # downgrade undoes in opposite order

    rev_id = str(int(time.time()))
    return TEMPLATE.format(
        rev_id=rev_id,
        down_revision=down_revision,
        create_date=time.strftime("%Y-%m-%d %H:%M:%S"),
        upgrade_body="\n".join(up_lines),
        downgrade_body="\n".join(down_lines),
    )


def get_current_head():
    """Read the current migration head directly from the versions folder,
    bypassing alembic.ini parsing entirely (avoids relying on a
    script_location key that Flask-Migrate may set programmatically in
    env.py instead of in the ini file).
    """
    from alembic.script import ScriptDirectory

    script = ScriptDirectory(str(PROJECT_ROOT / "migrations"))
    return script.get_current_head()


def main():
    app = create_app()
    with app.app_context():
        engine = db.engine
        model_checks = get_model_checks()
        db_checks = get_db_checks(engine)
        to_add, to_drop, to_replace = diff(model_checks, db_checks)

        if not (to_add or to_drop or to_replace):
            print("No CHECK constraint drift detected.")
            return

        print(f"Add: {len(to_add)}  Drop: {len(to_drop)}  Modify: {len(to_replace)}")
        for key, _ in to_add:
            print(f"  + {key}")
        for key, _ in to_drop:
            print(f"  - {key}")
        for key, *_ in to_replace:
            print(f"  ~ {key}")

        if "--debug" in sys.argv and to_replace:
            print("\n--- raw diffs for 'Modify' entries (before normalization) ---")
            for key, old_sql, new_sql in to_replace:
                print(f"\n{key}")
                print(f"  DB   : {old_sql!r}")
                print(f"  model: {new_sql!r}")
                print(f"  DB   normalized: {normalize_sql(old_sql)!r}")
                print(f"  model normalized: {normalize_sql(new_sql)!r}")

        down_revision = get_current_head()
        content = build_migration(to_add, to_drop, to_replace, down_revision)

        out_dir = PROJECT_ROOT / "migrations" / "versions"
        out_path = out_dir / f"{int(time.time())}_sync_check_constraints.py"
        out_path.write_text(content)
        print(f"\nWrote {out_path} -- review it, then run: flask db upgrade")


if __name__ == "__main__":
    main()