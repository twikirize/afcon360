"""Independently verify that the two CHECK-expression forms are logically
equivalent under PostgreSQL semantics, using a read-only SELECT.

No schema changes, no migrations.  Enumerates the relevant NULL/not-NULL
combinations for the exact ck_provider_participations_single_subject pair.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from sqlalchemy import text


def main():
    app = create_app()
    with app.app_context():
        engine = db.engine
        sql = text("""
            SELECT
                user_id,
                org_id,
                (user_id IS NOT NULL AND org_id IS NULL
                 OR user_id IS NULL AND org_id IS NOT NULL) AS form_a,
                ((user_id IS NOT NULL AND org_id IS NULL)
                 OR (user_id IS NULL AND org_id IS NOT NULL)) AS form_b
            FROM (
                VALUES
                    (NULL::integer, NULL::integer),
                    (NULL, 1),
                    (2, NULL),
                    (2, 3)
            ) AS t(user_id, org_id)
        """)
        rows = engine.connect().execute(sql).fetchall()

        for r in rows:
            print(
                f"  user_id={r[0]!s:>4}  org_id={r[1]!s:>4}  "
                f"form_a={r[2]!s:>5}  form_b={r[3]!s:>5}  "
                f"match={r[2] == r[3]}"
            )

        ok = all(r[2] == r[3] for r in rows)
        print()
        print("LOGICALLY EQUIVALENT:", ok)

        # Also verify the precedence claim at the pure-boolean level:
        rows2 = engine.connect().execute(text("""
            SELECT
                a, b, c, d,
                (a AND b OR c AND d) AS flat,
                ((a AND b) OR (c AND d)) AS grouped
            FROM (
                SELECT * FROM (VALUES (false), (true)) x(a)
                CROSS JOIN (VALUES (false), (true)) y(b)
                CROSS JOIN (VALUES (false), (true)) z(c)
                CROSS JOIN (VALUES (false), (true)) w(d)
            ) t
        """)).fetchall()
        ok2 = all(r[4] == r[5] for r in rows2)
        mismatches = [r for r in rows2 if r[4] != r[5]]
        print()
        print("A AND B OR C AND D == (A AND B) OR (C AND D) "
              f"over all 16 boolean combos: {ok2}")
        print("mismatches:", len(mismatches))


if __name__ == "__main__":
    main()