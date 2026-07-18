"""
Identity Security Audit

Purpose:
- Audit database identity consistency.
- Detect BIGINT/UUID/public_id mixing risks.
- Detect suspicious foreign key patterns.
- Generate JSON report.

SAFE:
- Read-only.
- Does not modify schema.
"""

import os
import sys
import json
from datetime import datetime, timezone

# -------------------------------------------------
# Ensure project root is importable
# -------------------------------------------------

BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../..")
)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


from sqlalchemy import inspect

from app import create_app
from app.extensions import db


REPORT_DIR = os.path.join(
    BASE_DIR,
    "reports",
    "security"
)

os.makedirs(REPORT_DIR, exist_ok=True)


# -------------------------------------------------
# Helpers
# -------------------------------------------------

def normalize_type(column_type):
    """
    SQLAlchemy type normalizer.
    """
    try:
        return str(column_type).upper()
    except Exception:
        return "UNKNOWN"


def is_identity_column(name):
    keywords = [
        "user_id",
        "owner_id",
        "creator_id",
        "actor_id",
        "member_id",
        "account_id",
        "transaction_id",
        "public_id",
    ]

    return any(
        key in name.lower()
        for key in keywords
    )


# -------------------------------------------------
# Audit Engine
# -------------------------------------------------

def audit_database():

    inspector = inspect(db.engine)

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "database": str(
            db.engine.url.database
        ),

        "summary": {
            "tables": 0,
            "identity_warnings": 0,
            "foreign_key_warnings": 0,
        },

        "tables": [],

        "warnings": []
    }


    tables = inspector.get_table_names()

    report["summary"]["tables"] = len(tables)


    for table in tables:

        table_info = {
            "table": table,
            "columns": [],
            "foreign_keys": []
        }


        columns = inspector.get_columns(table)


        column_map = {}


        for column in columns:

            name = column["name"]
            datatype = normalize_type(
                column["type"]
            )

            column_map[name] = datatype


            table_info["columns"].append(
                {
                    "name": name,
                    "type": datatype,
                    "nullable": column.get(
                        "nullable"
                    )
                }
            )


            # -------------------------------
            # Identity mismatch detection
            # -------------------------------

            if is_identity_column(name):

                if (
                    "UUID" in datatype
                    and name.endswith("_id")
                ):
                    pass


                if (
                    "BIGINT" in datatype
                    and (
                        "public"
                        in name.lower()
                    )
                ):

                    report["warnings"].append(
                        {
                            "type":
                            "IDENTITY_MISMATCH",

                            "table":
                            table,

                            "column":
                            name,

                            "issue":
                            "public identity stored as BIGINT"
                        }
                    )

                    report["summary"][
                        "identity_warnings"
                    ] += 1



        # -------------------------------
        # Foreign keys
        # -------------------------------

        foreign_keys = inspector.get_foreign_keys(
            table
        )


        for fk in foreign_keys:

            item = {
                "columns":
                    fk.get("constrained_columns"),

                "references":
                    fk.get("referred_table"),

                "target_columns":
                    fk.get("referred_columns")
            }


            table_info["foreign_keys"].append(
                item
            )


            source_cols = (
                fk.get("constrained_columns")
                or []
            )

            target_cols = (
                fk.get("referred_columns")
                or []
            )


            for source, target in zip(
                source_cols,
                target_cols
            ):

                source_type = (
                    column_map.get(
                        source,
                        ""
                    )
                )


                if (
                    "public_id" in target
                    and
                    "BIGINT" in source_type
                ):

                    report["warnings"].append(
                        {
                            "type":
                            "FOREIGN_KEY_ID_MIX",

                            "table":
                            table,

                            "column":
                            source,

                            "issue":
                            "BIGINT references public_id"
                        }
                    )


                    report["summary"][
                        "foreign_key_warnings"
                    ] += 1



        report["tables"].append(
            table_info
        )


    return report



# -------------------------------------------------
# Main
# -------------------------------------------------

if __name__ == "__main__":

    app = create_app()


    with app.app_context():

        result = audit_database()


        filename = (
            "identity_audit_"
            +
            datetime.now(
                timezone.utc
            ).strftime(
                "%Y%m%d_%H%M%S"
            )
            +
            ".json"
        )


        path = os.path.join(
            REPORT_DIR,
            filename
        )


        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                result,
                f,
                indent=4,
                default=str
            )


        print()
        print("=" * 60)
        print("IDENTITY AUDIT COMPLETE")
        print("=" * 60)
        print(
            f"Report created:"
        )
        print(path)
        print()
        print(
            "Tables scanned:",
            result["summary"]["tables"]
        )

        print(
            "Identity warnings:",
            result["summary"][
                "identity_warnings"
            ]
        )

        print(
            "Foreign key warnings:",
            result["summary"][
                "foreign_key_warnings"
            ]
        )
        print("=" * 60)