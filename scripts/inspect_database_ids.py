"""
Database-level ID inspection.

Uses PostgreSQL information_schema.

Read-only.
"""

from sqlalchemy import text

from app import create_app
from app.extensions import db


SQL = """
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE column_name LIKE '%id%'
ORDER BY table_name, column_name;
"""


def main():

    app = create_app()

    with app.app_context():

        rows = db.session.execute(
            text(SQL)
        ).fetchall()


        with open(
            "reports/database_id_inventory.md",
            "w"
        ) as f:

            f.write(
                "# Database ID Inventory\n\n"
            )

            for row in rows:

                f.write(
                    f"""
## {row.table_name}.{row.column_name}

Type:
{row.data_type}

Nullable:
{row.is_nullable}

---
"""
                )


    print(
        "Created reports/database_id_inventory.md"
    )


if __name__ == "__main__":
    main()
    