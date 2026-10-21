from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from scripts.h3 import build_h3_candidate as builder


_CANDIDATE_DATABASE = re.compile(r"^afcon360_h3_candidate(?:_[a-z0-9][a-z0-9-]*)?_test$")


def _read_candidate_state(url: URL) -> dict[str, Any]:
    engine = create_engine(
        url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 5, "options": "-c default_transaction_read_only=on"},
    )
    try:
        with engine.connect() as connection:
            server_version = str(connection.execute(text("SHOW server_version")).scalar_one())
            revisions = list(
                connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars()
            )
            public_tables = int(
                connection.execute(
                    text("SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
                ).scalar_one()
            )
            public_enums = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_catalog.pg_type AS t
                        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
                        WHERE n.nspname = 'public' AND t.typtype = 'e'
                        """
                    )
                ).scalar_one()
            )
            all_user_tables = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_catalog.pg_class AS c
                        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                        WHERE n.nspname !~ '^pg_'
                          AND n.nspname <> 'information_schema'
                          AND c.relkind IN ('r', 'p')
                        """
                    )
                ).scalar_one()
            )
            all_user_enums = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_catalog.pg_type AS t
                        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
                        WHERE n.nspname !~ '^pg_'
                          AND n.nspname <> 'information_schema'
                          AND t.typtype = 'e'
                        """
                    )
                ).scalar_one()
            )
    except Exception as exc:
        raise RuntimeError(
            "Read-only parity preflight failed. Check the approved local source and candidate databases; connection details were withheld."
        ) from exc
    finally:
        engine.dispose()

    if not builder._SOURCE_SERVER_VERSION.match(server_version):
        raise ValueError(f"Expected PostgreSQL {builder.APPROVED_SOURCE_SERVER_VERSION}; observed {server_version!r}.")
    if public_tables != builder.EXPECTED_PUBLIC_TABLES:
        raise ValueError(
            f"Expected {builder.EXPECTED_PUBLIC_TABLES} public tables including alembic_version; observed {public_tables}."
        )
    if public_enums != builder.EXPECTED_PUBLIC_ENUMS:
        raise ValueError(
            f"Expected {builder.EXPECTED_PUBLIC_ENUMS} public enum types; observed {public_enums}."
        )
    return {
        "server_version": server_version,
        "revisions": revisions,
        "public_table_count_including_alembic_version": public_tables,
        "public_enum_count": public_enums,
        "all_user_schema_table_count_including_alembic_version": all_user_tables,
        "all_user_schema_enum_count": all_user_enums,
    }


def _dump_schema(url: URL, pg_dump_executable: str) -> tuple[str, str]:
    environment = builder._pg_dump_environment(url)
    version_result = subprocess.run(
        [pg_dump_executable, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=environment,
        check=False,
    )
    if version_result.returncode != 0:
        raise RuntimeError("Could not identify pg_dump client version.")
    version_match = re.search(r"\b(\d+)\.(\d+)\b", version_result.stdout)
    if not version_match or int(version_match.group(1)) != 18:
        raise RuntimeError("Use a PostgreSQL 18 pg_dump client for the first H3 parity comparison.")

    result = subprocess.run(
        [
            pg_dump_executable,
            "--schema-only",
            "--no-owner",
            "--no-privileges",
            "--quote-all-identifiers",
            "--exclude-table=public.alembic_version",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=300,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Schema-only pg_dump failed; no database was changed and diagnostics were withheld.")
    return builder.normalize_schema_dump(result.stdout), version_match.group(0)


def compare_schema_texts(source_sql: str, candidate_sql: str) -> dict[str, Any]:
    source_hash = hashlib.sha256(source_sql.encode("utf-8")).hexdigest()
    candidate_hash = hashlib.sha256(candidate_sql.encode("utf-8")).hexdigest()
    diff = list(
        difflib.unified_diff(
            source_sql.splitlines(),
            candidate_sql.splitlines(),
            fromfile="H2-prime-source",
            tofile="H3-candidate",
            n=3,
            lineterm="",
        )
    )
    return {
        "match": source_sql == candidate_sql,
        "source_sha256": source_hash,
        "candidate_sha256": candidate_hash,
        "difference_line_count": len(diff),
        "diff_lines": diff,
    }


def compare_candidate(candidate_database: str, pg_dump_executable: str = "pg_dump") -> dict[str, Any]:
    if not _CANDIDATE_DATABASE.fullmatch(candidate_database):
        raise ValueError("Candidate database must match afcon360_h3_candidate*_test.")
    executable = shutil.which(pg_dump_executable)
    if not executable:
        raise RuntimeError("pg_dump was not found; pass --pg-dump with its full path.")

    source_url = builder._connection_url_from_local_config(
        environment_key="H3_BASELINE_SOURCE_DATABASE_URL",
        target_database=builder.APPROVED_SOURCE_DATABASE,
        allow_database_retarget=True,
    )
    candidate_url = builder._connection_url_from_local_config(
        environment_key="H3_CANDIDATE_DATABASE_URL",
        target_database=candidate_database,
        allow_database_retarget=True,
    )

    source_state = builder._source_preflight(source_url)
    candidate_state = _read_candidate_state(candidate_url)

    if candidate_state["revisions"] != [builder.CANDIDATE_REVISION]:
        raise ValueError(
            f"Candidate must be at {builder.CANDIDATE_REVISION}; observed {candidate_state['revisions']!r}."
        )
    if candidate_state["server_version"] != source_state["server_version"]:
        raise ValueError("Source and candidate must use the same PostgreSQL patch version for this first comparison.")
    if (
        candidate_state["all_user_schema_table_count_including_alembic_version"]
        != source_state["all_user_schema_table_count_including_alembic_version"]
    ):
        raise ValueError("Source and candidate relation counts differ; inspect before comparing definitions.")
    if candidate_state["all_user_schema_enum_count"] != source_state["all_user_schema_enum_count"]:
        raise ValueError("Source and candidate enum counts differ; inspect before comparing definitions.")

    source_sql, source_dump_version = _dump_schema(source_url, executable)
    candidate_sql, candidate_dump_version = _dump_schema(candidate_url, executable)
    if source_dump_version != candidate_dump_version:
        raise ValueError("Source and candidate dumps must use the same pg_dump client version.")
    source_expected_tables = source_state["all_user_schema_table_count_including_alembic_version"] - 1
    source_expected_enums = source_state["all_user_schema_enum_count"]
    builder.validate_schema_sql(
        source_sql, expected_tables=source_expected_tables, expected_enums=source_expected_enums
    )
    builder.validate_schema_sql(
        candidate_sql, expected_tables=source_expected_tables, expected_enums=source_expected_enums
    )

    comparison = compare_schema_texts(source_sql, candidate_sql)
    report: dict[str, Any] = {
        "gate": "PASS" if comparison["match"] else "FAIL",
        "source_database": builder.APPROVED_SOURCE_DATABASE,
        "source_revision": builder.APPROVED_SOURCE_REVISION,
        "candidate_database": candidate_database,
        "candidate_revision": builder.CANDIDATE_REVISION,
        "postgresql_version": source_state["server_version"],
        "pg_dump_version": source_dump_version,
        "public_tables_including_alembic_version": source_state["public_table_count_including_alembic_version"],
        "public_enum_count": source_state["public_enum_count"],
        "source_schema_sha256": comparison["source_sha256"],
        "candidate_schema_sha256": comparison["candidate_sha256"],
        "schema_exact_match": comparison["match"],
        "difference_line_count": comparison["difference_line_count"],
        "database_access": "read-only on both explicitly named local databases",
        "protected_databases_contacted": False,
    }
    if not comparison["match"]:
        diff_path = Path(tempfile.gettempdir()) / "afcon360_h3_candidate_schema.diff"
        diff_path.write_text("\n".join(comparison["diff_lines"]) + "\n", encoding="utf-8", newline="\n")
        report["diff_path"] = str(diff_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare H3 candidate schema to the approved local H2-prime migration replay."
    )
    parser.add_argument("--candidate-database", default="afcon360_h3_candidate_test")
    parser.add_argument("--pg-dump", default="pg_dump")
    args = parser.parse_args(argv)
    try:
        report = compare_candidate(args.candidate_database, args.pg_dump)
    except (ValueError, FileExistsError, RuntimeError) as exc:
        # Explicit validation messages contain no connection URL or credential.
        print(f"H3 schema comparison BLOCKED: {exc} No database was modified.")
        return 2
    except Exception as exc:
        # Driver/subprocess exceptions may contain connection details; reveal only the class.
        print(f"H3 schema comparison BLOCKED: {type(exc).__name__}. No database was modified.")
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
