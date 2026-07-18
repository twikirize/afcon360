"""
Read-only ID field inventory.

Finds all SQLAlchemy columns containing "_id"
and classifies them using schema metadata.

No database writes.
No migrations.
No model changes.
"""

import os
import importlib
import inspect
from sqlalchemy import ForeignKey

from app import create_app
from app.extensions import db


REPORT = "reports/id_field_inventory.md"


def discover_models():
    models = []

    for root, _, files in os.walk("app"):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)

                module_name = (
                    path.replace("/", ".")
                    .replace("\\", ".")
                    .replace(".py", "")
                )

                try:
                    module = importlib.import_module(module_name)

                    for _, obj in inspect.getmembers(module):
                        if (
                            inspect.isclass(obj)
                            and hasattr(obj, "__table__")
                            and obj.__module__ == module.__name__
                        ):
                            models.append(obj)

                except Exception:
                    pass

    return models


def classify_column(column):

    if column.primary_key:
        return "PRIMARY_KEY"

    if column.foreign_keys:
        return "FOREIGN_KEY"

    if column.name == "public_id":
        return "PUBLIC_UUID"

    if column.name.endswith("_id"):
        return "BUSINESS_IDENTIFIER"

    return "OTHER"


def main():

    app = create_app()

    with app.app_context():

        models = discover_models()

        lines = []

        lines.append("# ID Field Inventory\n")

        for model in sorted(models, key=lambda x: x.__name__):

            for column in model.__table__.columns:

                if "_id" in column.name:

                    fk = ""

                    if column.foreign_keys:
                        fk = ",".join(
                            str(x.target)
                            for x in column.foreign_keys
                        )

                    lines.append(
                        f"""
## {model.__name__}.{column.name}

- Type: `{column.type}`
- Nullable: `{column.nullable}`
- Indexed: `{column.index}`
- Foreign Key: `{fk or "NO"}`
- Classification: `{classify_column(column)}`
"""
                    )

        os.makedirs("reports", exist_ok=True)

        with open(REPORT, "w") as f:
            f.write("\n".join(lines))

        print(f"Created {REPORT}")


if __name__ == "__main__":
    main()