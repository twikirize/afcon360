from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover - the explicit environment variable still works
    dotenv_values = None


APPROVED_SOURCE_DATABASE = "afcon360_h2p_replay_20261018_test"
APPROVED_SOURCE_REVISION = "df55cbe3f516"
APPROVED_SOURCE_SERVER_VERSION = "18.4"
EXPECTED_PUBLIC_TABLES = 224  # Includes Alembic's own version table.
EXPECTED_PUBLIC_ENUMS = 49
# Recorded SHA-256 of the source schema after normalisation.
# This must be updated (with --accept-sha-change) after an intentional normaliser change;
# see the docstring on normalise_schema_dump for the current canonicalisation rules.
APPROVED_SOURCE_SCHEMA_SHA256 = "0701c42dda041f3725c59d2b8081fd4534b5f8d3359f67839aad98c8d53198da"
CANDIDATE_REVISION = "h3a20261020"
CANDIDATE_OUTPUT = Path("migrations/h3_candidate/versions/h3a20261020_static_baseline.py")

_HEADER_LINES = (
    re.compile(r"^\s*-- PostgreSQL database dump\s*$", re.IGNORECASE),
    re.compile(r"^\s*-- PostgreSQL database dump complete\s*$", re.IGNORECASE),
    re.compile(r"^\s*-- Dumped from database version .*$", re.IGNORECASE),
    re.compile(r"^\s*-- Dumped by pg_dump version .*$", re.IGNORECASE),
    re.compile(r"^\s*-- Started on .*$", re.IGNORECASE),
    re.compile(r"^\s*-- Completed on .*$", re.IGNORECASE),
)
_PUBLIC_SCHEMA_CREATE = re.compile(
    r'^\s*CREATE\s+SCHEMA\s+(?:"public"|public)\s*;\s*$', re.IGNORECASE
)
_PUBLIC_SCHEMA_OWNER = re.compile(
    r'^\s*ALTER\s+SCHEMA\s+(?:"public"|public)\s+OWNER\s+TO\s+[^;]+\s*;\s*$',
    re.IGNORECASE,
)
_PSQL_META = re.compile(r"^\s*\\([A-Za-z]+)\b")
_COPY_DATA = re.compile(r"^\s*COPY\s+.+\s+FROM\s+stdin\s*;\s*$", re.IGNORECASE)
_CREATE_TABLE = re.compile(
    r'^\s*CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?',
    re.IGNORECASE | re.MULTILINE,
)
_CREATE_ENUM = re.compile(
    r'^\s*CREATE\s+TYPE\s+(?:(?:"[^"]+"|[A-Za-z_][\w$]*)\s*\.\s*)?'
    r'(?:"[^"]+"|[A-Za-z_][\w$]*)\s+AS\s+ENUM\b',
    re.IGNORECASE | re.MULTILINE,
)
_SOURCE_SERVER_VERSION = re.compile(r"^18\.4(?:\D|$)")

# PostgreSQL deparse variance: pg_dump renders `= ANY((ARRAY[...])::text[])` from the source
# database, while applying that same SQL to a fresh database and re-dumping produces
# `= ANY(ARRAY[(...)::text, ...])`. The two forms are semantically identical — PostgreSQL
# rejects and accepts exactly the same values — but the textual rendering differs. This
# pattern matches the source form so it can be canonicalised to the per-element form.
# Matches both 'character varying' and 'varchar', and handles SQL-escaped apostrophes ('').
_SOURCE_ARRAY_CAST = re.compile(
    r"\(ARRAY\["
    r"((?:'(?:[^']|'')*'|\"[^\"]+\")::(?:character varying|varchar)"
    r"(?:,\s*(?:'(?:[^']|'')*'|\"[^\"]+\")::(?:character varying|varchar))*)"
    r"\]\)::\"text\"\[\]"
)


def _canonicalize_array_cast(match: re.Match) -> str:
    """Convert `(ARRAY['x'::varchar, ...])::"text"[]` to `ARRAY[('x'::varchar)::"text", ...]`."""
    body = match.group(1)
    body = re.sub(
        r"('(?:[^']|'')*'|\"[^\"]+\")::(?:character varying|varchar)",
        r'(\1::character varying)::"text"',
        body,
    )
    return f"ARRAY[{body}]"


def _dotenv_values() -> dict[str, Any]:
    if dotenv_values is None:
        return {}
    try:
        return dict(dotenv_values(".env"))
    except (OSError, UnicodeError):
        return {}


def _connection_url_from_local_config(
    *, environment_key: str, target_database: str, allow_database_retarget: bool
) -> URL:
    raw = os.environ.get(environment_key)
    explicit = bool(raw)
    if not raw:
        values = _dotenv_values()
        raw = (
            os.environ.get("TEST_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or os.environ.get("SQLALCHEMY_DATABASE_URI")
            or values.get("TEST_DATABASE_URL")
            or values.get("DATABASE_URL")
            or values.get("SQLALCHEMY_DATABASE_URI")
        )
    if not raw:
        raise ValueError(
            f"Set {environment_key} or provide a local test URL in the existing environment configuration."
        )

    url = make_url(str(raw))
    if url.get_backend_name() != "postgresql":
        raise ValueError("H3 candidate authoring requires PostgreSQL; no database connection was made.")
    if (url.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("H3 candidate authoring is restricted to a loopback PostgreSQL server.")
    if allow_database_retarget and not explicit:
        # Reuse only local test credentials, but force a specifically approved database name.
        url = url.set(database=target_database)
    if url.database != target_database:
        raise ValueError(f"The connection must target exactly {target_database!r}.")
    return url


def validate_source_identity(*, database: str, revision: str, server_version: str) -> None:
    if database != APPROVED_SOURCE_DATABASE:
        raise ValueError("Only the approved disposable H2-prime replay can be a source.")
    if revision != APPROVED_SOURCE_REVISION:
        raise ValueError("The source Alembic revision is not the approved replay head.")
    if not _SOURCE_SERVER_VERSION.match(server_version):
        raise ValueError("The source server version is not the recorded PostgreSQL 18.4 version.")


def _source_preflight(url: URL) -> dict[str, Any]:
    engine = create_engine(
        url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 5, "options": "-c default_transaction_read_only=on"},
    )
    try:
        with engine.connect() as connection:
            server_version = str(connection.execute(text("SHOW server_version")).scalar_one())
            server_encoding = str(connection.execute(text("SHOW server_encoding")).scalar_one())
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
        # Do not print connection URLs or driver diagnostics that might contain connection details.
        raise RuntimeError(
            "Read-only source preflight failed. Check local credentials and the approved disposable replay database; connection details were withheld."
        ) from exc
    finally:
        engine.dispose()

    validate_source_identity(
        database=APPROVED_SOURCE_DATABASE,
        revision=revisions[0] if len(revisions) == 1 else "",
        server_version=server_version,
    )
    if server_encoding.upper() != "UTF8":
        raise ValueError("The approved H2-prime source must use UTF8 encoding for reproducible disposable replay.")
    if public_tables != EXPECTED_PUBLIC_TABLES:
        raise ValueError(
            f"Expected {EXPECTED_PUBLIC_TABLES} public tables including alembic_version; observed {public_tables}."
        )
    if public_enums != EXPECTED_PUBLIC_ENUMS:
        raise ValueError(
            f"Expected {EXPECTED_PUBLIC_ENUMS} public enum types; observed {public_enums}."
        )
    return {
        "source_database": APPROVED_SOURCE_DATABASE,
        "source_revision": APPROVED_SOURCE_REVISION,
        "server_version": server_version,
        "server_encoding": server_encoding,
        "public_table_count_including_alembic_version": public_tables,
        "public_enum_count": public_enums,
        "all_user_schema_table_count_including_alembic_version": all_user_tables,
        "all_user_schema_enum_count": all_user_enums,
    }


def _pg_dump_environment(url: URL) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PGHOST"] = str(url.host)
    environment["PGPORT"] = str(url.port or 5432)
    environment["PGDATABASE"] = str(url.database)
    if url.username:
        environment["PGUSER"] = url.username
    if url.password is not None:
        environment["PGPASSWORD"] = url.password
    sslmode = url.query.get("sslmode")
    if isinstance(sslmode, str) and sslmode:
        environment["PGSSLMODE"] = sslmode
    # pg_dump may only read from the approved source database.
    environment["PGOPTIONS"] = "-c default_transaction_read_only=on"
    return environment


def normalize_schema_dump(raw_dump: str) -> str:
    """Remove pg_dump's non-SQL wrappers and normalise variations that are not part of the schema.

    Current normalisations:
      * Strip psql-only wrapper commands (\\restrict, \\unrestrict) and pg_dump header lines.
      * Strip CREATE SCHEMA public / ALTER SCHEMA public OWNER TO … (a fresh PostgreSQL
        database already provides these).
      * Rewrite "Owner: <name>" comments to "Owner: <normalized>".
      * Canonicalise the array-cast rendering of CHECK / partial-index WHERE clauses:
          source form:  (ARRAY['x'::character varying, ...])::"text"[]
          applied form: ARRAY[('x'::character varying)::"text", ...]
        Both forms are semantically identical; they differ only because PostgreSQL re-deparses
        the expression tree during pg_dump. Without this rule, an otherwise correct H3
        baseline fails the byte-for-byte schema comparison on every CHECK constraint.
    """
    retained: list[str] = []
    for line in raw_dump.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        if any(pattern.match(line) for pattern in _HEADER_LINES):
            continue
        if line.lstrip().startswith("-- Name:"):
            line = re.sub(r"; Owner: .*?$", "; Owner: <normalized>", line)
        if re.match(r"^\s*\\(?:restrict|unrestrict)\b", line):
            # These psql client commands are not SQL and are not accepted by DBAPI execution.
            continue
        meta = _PSQL_META.match(line)
        if meta:
            raise ValueError(
                f"Unexpected psql-only command \\{meta.group(1)} in schema dump; candidate generation stopped."
            )
        if _PUBLIC_SCHEMA_CREATE.match(line) or _PUBLIC_SCHEMA_OWNER.match(line):
            # A newly created PostgreSQL database already has its public schema.
            continue
        # Canonicalise PostgreSQL deparse variance in CHECK / WHERE array casts.
        line = _SOURCE_ARRAY_CAST.sub(_canonicalize_array_cast, line)
        retained.append(line)

    sql = "\n".join(retained).strip() + "\n"
    if re.search(r"\balembic_version\b", sql, re.IGNORECASE):
        raise ValueError("The schema dump contains alembic_version; it must be excluded from the baseline.")
    if any(_COPY_DATA.match(line) for line in sql.splitlines()):
        raise ValueError("The input appears to contain table data; only a schema-only dump is permitted.")
    return sql


def validate_schema_sql(
    sql: str, *, expected_tables: int, expected_enums: int, minimum_size: bool = True
) -> dict[str, int]:
    if re.search(r"\balembic_version\b", sql, re.IGNORECASE):
        raise ValueError("The candidate must not create or reference public.alembic_version.")
    if any(_COPY_DATA.match(line) for line in sql.splitlines()):
        raise ValueError("Data-bearing COPY commands are forbidden in an H3 baseline.")
    tables = len(_CREATE_TABLE.findall(sql))
    enums = len(_CREATE_ENUM.findall(sql))
    if tables != expected_tables:
        raise ValueError(
            f"Schema dump table count mismatch: expected {expected_tables}, found {tables}."
        )
    if enums != expected_enums:
        raise ValueError(
            f"Schema dump enum count mismatch: expected {expected_enums}, found {enums}."
        )
    if minimum_size and (tables < 200 or enums < 40):
        raise ValueError("The dump is too small to represent the recorded AFCON360 schema.")
    return {"table_ddl_count": tables, "enum_ddl_count": enums}


def render_candidate_migration(
    sql: str, *, server_version: str, pg_dump_version: str, source_sha256: str
) -> str:
    # Emit one safely escaped Python string literal per dump line. SQL quoting and
    # dollar-quoted function bodies are preserved byte-for-byte after newline normalization.
    sql_lines = sql.splitlines(keepends=True)
    sql_literal_lines = "\n".join(f"    {line!r}" for line in sql_lines)
    if not sql_literal_lines:
        raise ValueError("Refusing to render an empty baseline.")
    return (
        '"""Candidate H3/N-squash static baseline; generated from the approved H2-prime replay.\n'
        f"Source database: {APPROVED_SOURCE_DATABASE}\n"
        f"Source Alembic revision: {APPROVED_SOURCE_REVISION}\n"
        f"Source PostgreSQL version: {server_version}\n"
        f"pg_dump client version: {pg_dump_version}\n"
        f"Normalized schema SQL SHA-256: {source_sha256}\n"
        "This file is isolated under migrations/h3_candidate and is not the active application migration chain.\n"
        'Review and disposable replay are required before any activation.\n"""\n'
        "from alembic import op\n\n"
        "revision = " + repr(CANDIDATE_REVISION) + "\n"
        "down_revision = None\n"
        "branch_labels = None\n"
        "depends_on = None\n\n"
        "_SCHEMA_SQL = (\n"
        + sql_literal_lines
        + "\n)\n\n"
        "def upgrade():\n"
        "    op.get_bind().exec_driver_sql(\n"
        "        _SCHEMA_SQL, execution_options={\"no_parameters\": True}\n"
        "    )\n"
        "def downgrade():\n"
        "    raise NotImplementedError(\n"
        "        'H3 baseline downgrade is intentionally disabled; recovery requires a verified backup restore.'\n"
        "    )\n"
    )


def build_candidate(
    *,
    replace: bool = False,
    pg_dump_executable: str = "pg_dump",
    accept_sha_change: bool = False,
) -> dict[str, Any]:
    url = _connection_url_from_local_config(
        environment_key="H3_BASELINE_SOURCE_DATABASE_URL",
        target_database=APPROVED_SOURCE_DATABASE,
        allow_database_retarget=True,
    )
    source = _source_preflight(url)

    executable = shutil.which(pg_dump_executable)
    if not executable:
        raise RuntimeError(
            "pg_dump was not found. Add the PostgreSQL 18 bin directory to PATH or pass --pg-dump with its full path."
        )
    environment = _pg_dump_environment(url)
    version_result = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=environment,
        check=False,
    )
    if version_result.returncode != 0:
        raise RuntimeError("Could not identify the pg_dump version; no candidate was written.")
    match = re.search(r"\b(\d+)\.(\d+)\b", version_result.stdout)
    if not match or int(match.group(1)) != 18:
        raise RuntimeError(
            "Use a PostgreSQL 18 pg_dump client for this first capture; no candidate was written."
        )
    pg_dump_version = match.group(0)

    dump_result = subprocess.run(
        [
            executable,
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
    if dump_result.returncode != 0:
        raise RuntimeError(
            "pg_dump failed against the approved disposable source. No candidate was written; diagnostic output was withheld."
        )

    sql = normalize_schema_dump(dump_result.stdout)
    expected_tables = source["all_user_schema_table_count_including_alembic_version"] - 1
    expected_enums = source["all_user_schema_enum_count"]
    counts = validate_schema_sql(sql, expected_tables=expected_tables, expected_enums=expected_enums)
    digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()

    if digest != APPROVED_SOURCE_SCHEMA_SHA256 and not accept_sha_change:
        raise ValueError(
            "The approved H2-prime schema hash changed after normalization. "
            f"Expected: {APPROVED_SOURCE_SCHEMA_SHA256} | Computed: {digest}. "
            "If this is an intentional normalizer change (e.g. adding a canonicalization rule), "
            "review the complete schema diff, rerun with --accept-sha-change, and update "
            "APPROVED_SOURCE_SCHEMA_SHA256 in build_h3_candidate.py to the new value. "
            "If the source database itself drifted, preserve the output and investigate before proceeding."
        )

    rendered = render_candidate_migration(
        sql,
        server_version=source["server_version"],
        pg_dump_version=pg_dump_version,
        source_sha256=digest,
    )

    output = CANDIDATE_OUTPUT
    if output.exists() and not replace:
        raise FileExistsError(
            f"{output} already exists. Review/preserve it first; pass --replace only when intentionally regenerating this candidate."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")

    return {
        **source,
        "pg_dump_version": pg_dump_version,
        **counts,
        "normalized_schema_sql_sha256": digest,
        "sha_matches_approved": digest == APPROVED_SOURCE_SCHEMA_SHA256,
        "candidate_path": output.as_posix(),
        "candidate_bytes": output.stat().st_size,
        "source_access": "read-only; approved disposable replay only",
        "active_migration_chain_changed": False,
        "protected_databases_contacted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an isolated H3 candidate from the approved local H2-prime PostgreSQL replay."
    )
    parser.add_argument(
        "--pg-dump",
        default="pg_dump",
        help="pg_dump executable or full path to the PostgreSQL 18 client.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Explicitly replace only the isolated generated H3 candidate file.",
    )
    parser.add_argument(
        "--accept-sha-change",
        action="store_true",
        help=(
            "Allow the computed schema SHA-256 to differ from APPROVED_SOURCE_SCHEMA_SHA256. "
            "Use only when the change is an intentional normalizer update; update the constant "
            "in build_h3_candidate.py to the new value afterward."
        ),
    )
    args = parser.parse_args(argv)
    try:
        report = build_candidate(
            replace=args.replace,
            pg_dump_executable=args.pg_dump,
            accept_sha_change=args.accept_sha_change,
        )
    except (ValueError, FileExistsError, RuntimeError) as exc:
        # These validation/operational messages are authored here and contain no connection URL.
        print(f"H3 candidate generation BLOCKED: {exc} No protected database was modified.")
        return 2
    except Exception as exc:
        # Driver/subprocess exceptions may contain connection details; reveal only the class.
        print(f"H3 candidate generation BLOCKED: {type(exc).__name__}. No protected database was modified.")
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())