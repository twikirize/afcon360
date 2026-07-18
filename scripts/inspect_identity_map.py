"""
Inspect database identity columns.

Shows:
- id columns
- user_id columns
- account_id columns
- owner columns
- FK relationships
"""

from sqlalchemy import inspect

from app import create_app
from app.extensions import db


def inspect_identity():

    inspector = inspect(db.engine)

    print("\n=== IDENTITY INVENTORY ===\n")

    for table in sorted(inspector.get_table_names()):

        columns = inspector.get_columns(table)

        interesting = []

        for column in columns:
            name = column["name"].lower()

            if any(keyword in name for keyword in [
                "id",
                "user",
                "account",
                "owner",
                "organisation",
                "organization"
            ]):
                interesting.append(column)

        if not interesting:
            continue

        print(f"\nTABLE: {table}")
        print("-" * 60)

        for column in interesting:
            print(
                f"{column['name']:35}"
                f"{str(column['type']):25}"
                f" nullable={column['nullable']}"
            )

        # Foreign keys
        fks = inspector.get_foreign_keys(table)

        if fks:
            print("\nForeign Keys:")

            for fk in fks:
                print(
                    f"  {fk['constrained_columns']} "
                    f"-> "
                    f"{fk['referred_table']}."
                    f"{fk['referred_columns']}"
                )


if __name__ == "__main__":

    app = create_app()

    with app.app_context():
        inspect_identity()