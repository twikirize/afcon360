from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from scripts.h3 import build_h3_candidate as builder


REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_PATH = REPO_ROOT / builder.CANDIDATE_OUTPUT
ALEMBIC_CONFIG_PATH = REPO_ROOT / "migrations" / "h3_candidate" / "alembic.ini"
CANDIDATE_DATABASE_PATTERN = re.compile(
    r"^afcon360_h3_candidate(?:_[a-z0-9][a-z0-9-]*)?_test$"
)
POSTGRESQL_18_4_PATTERN = re.compile(r"^18\.4(?:\D|$)")


def validate_candidate_database_name(name: str) -> str:
    if not CANDIDATE_DATABASE_PATTERN.fullmatch(name):
        raise ValueError(
            "Candidate database must match afcon360_h3_candidate*_test; "
            "protected application databases are never valid targets."
        )
    return name


def load_and_validate_candidate(
    path: Path = CANDIDATE_PATH,
    *,
    expected_sha256: str = builder.APPROVED_SOURCE_SCHEMA_SHA256,
) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Candidate artifact is missing at {path.as_posix()}; generate and review it first."
        )
    spec = importlib.util.spec_from_file_location("h3a_candidate_artifact", path)
    if spec is None or spec.loader is None:
        raise ValueError("Could not load the candidate migration artifact.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if getattr(module, "revision", None) != builder.CANDIDATE_REVISION:
        raise ValueError("Candidate revision does not match the approved H3-A candidate ID.")
    if getattr(module, "down_revision", "not-none") is not None:
        raise ValueError("H3-A candidate must be a single root revision with down_revision=None.")
    sql = getattr(module, "_SCHEMA_SQL", None)
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("Candidate does not contain the required static _SCHEMA_SQL payload.")
    digest_match = re.search(
        r"Normalized schema SQL SHA-256:\s*([0-9a-f]{64})",
        module.__doc__ or "",
    )
    if digest_match is None:
        raise ValueError("Candidate provenance header does not contain a normalized schema SHA-256.")
    actual_digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    expected_digest = digest_match.group(1)
    if actual_digest != expected_digest:
        raise ValueError(
            "Candidate SQL hash does not match its embedded provenance hash; preserve it and regenerate/review."
        )
    if actual_digest != expected_sha256:
        raise ValueError(
            "Candidate SQL hash differs from the pinned approved H2-prime schema hash; no database action was started."
        )
    if not callable(getattr(module, "upgrade", None)):
        raise ValueError("Candidate does not expose an Alembic upgrade() function.")

    return {
        "path": path.as_posix(),
        "revision": module.revision,
        "down_revision": module.down_revision,
        "schema_sql_sha256": actual_digest,
        "schema_sql_bytes": len(sql.encode("utf-8")),
        "module": module,
    }


def _resolve_candidate_url(candidate_database: str) -> URL:
    return builder._connection_url_from_local_config(
        environment_key="H3_CANDIDATE_DATABASE_URL",
        target_database=validate_candidate_database_name(candidate_database),
        allow_database_retarget=True,
    )


def _resolve_source_url() -> URL:
    return builder._connection_url_from_local_config(
        environment_key="H3_BASELINE_SOURCE_DATABASE_URL",
        target_database=builder.APPROVED_SOURCE_DATABASE,
        allow_database_retarget=True,
    )


def _maintenance_url(candidate_url: URL) -> URL:
    return candidate_url.set(database="postgres")


def _database_exists(candidate_url: URL) -> bool:
    engine = create_engine(
        _maintenance_url(candidate_url),
        poolclass=NullPool,
        connect_args={
            "connect_timeout": 5,
            "options": "-c default_transaction_read_only=on",
        },
    )
    try:
        with engine.connect() as connection:
            return (
                connection.execute(
                    text("SELECT 1 FROM pg_catalog.pg_database WHERE datname = :name"),
                    {"name": candidate_url.database},
                ).scalar_one_or_none()
                is not None
            )
    except Exception as exc:
        raise RuntimeError(
            "Could not verify the candidate database's existence through the local postgres maintenance database."
        ) from exc
    finally:
        engine.dispose()


def _maintenance_server_state(candidate_url: URL) -> dict[str, str]:
    engine = create_engine(
        _maintenance_url(candidate_url),
        poolclass=NullPool,
        connect_args={
            "connect_timeout": 5,
            "options": "-c default_transaction_read_only=on",
        },
    )
    try:
        with engine.connect() as connection:
            return {
                "server_version": str(connection.execute(text("SHOW server_version")).scalar_one()),
                "server_encoding": str(connection.execute(text("SHOW server_encoding")).scalar_one()),
            }
    except Exception as exc:
        raise RuntimeError(
            "Could not verify the local candidate PostgreSQL server before database creation."
        ) from exc
    finally:
        engine.dispose()


def _create_candidate_database(candidate_url: URL, source_encoding: str) -> None:
    if source_encoding.upper() != "UTF8":
        raise ValueError(
            f"Approved H2-prime source encoding is {source_encoding!r}, not UTF8; create no candidate database."
        )
    maintenance_url = _maintenance_url(candidate_url)
    engine = create_engine(maintenance_url, poolclass=NullPool, connect_args={"connect_timeout": 5})
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            exists = (
                connection.execute(
                    text("SELECT 1 FROM pg_catalog.pg_database WHERE datname = :name"),
                    {"name": candidate_url.database},
                ).scalar_one_or_none()
                is not None
            )
            if exists:
                raise ValueError(
                    "Candidate database already exists. It was not dropped, reset, or modified; inspect it or choose a new approved disposable name."
                )
            # The candidate name has passed a strict allowlist, so it is safe to quote as an identifier.
            connection.exec_driver_sql(
                f'CREATE DATABASE "{candidate_url.database}" WITH TEMPLATE template0 ENCODING \'UTF8\''
            )
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            "Candidate database creation failed. No protected database was targeted; check local CREATEDB permission."
        ) from exc
    finally:
        engine.dispose()


def _state(candidate_url: URL) -> dict[str, Any]:
    engine = create_engine(
        candidate_url,
        poolclass=NullPool,
        connect_args={
            "connect_timeout": 5,
            "options": "-c default_transaction_read_only=on",
        },
    )
    try:
        with engine.connect() as connection:
            server_version = str(connection.execute(text("SHOW server_version")).scalar_one())
            server_encoding = str(connection.execute(text("SHOW server_encoding")).scalar_one())
            relation_count = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_catalog.pg_class AS c
                        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                        WHERE n.nspname !~ '^pg_'
                          AND n.nspname <> 'information_schema'
                          AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
                        """
                    )
                ).scalar_one()
            )
            custom_type_count = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_catalog.pg_type AS t
                        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
                        WHERE n.nspname !~ '^pg_'
                          AND n.nspname <> 'information_schema'
                          AND t.typrelid = 0
                          AND t.typtype IN ('b', 'c', 'd', 'e', 'p', 'r')
                        """
                    )
                ).scalar_one()
            )
            routine_count = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_catalog.pg_proc AS p
                        JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                        WHERE n.nspname !~ '^pg_'
                          AND n.nspname <> 'information_schema'
                        """
                    )
                ).scalar_one()
            )
            extension_count = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_catalog.pg_extension AS e
                        JOIN pg_catalog.pg_namespace AS n ON n.oid = e.extnamespace
                        WHERE n.nspname !~ '^pg_'
                          AND n.nspname <> 'information_schema'
                        """
                    )
                ).scalar_one()
            )
            extra_schema_count = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_catalog.pg_namespace
                        WHERE nspname !~ '^pg_'
                          AND nspname <> 'information_schema'
                          AND nspname <> 'public'
                        """
                    )
                ).scalar_one()
            )
            public_table_count = int(
                connection.execute(
                    text("SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
                ).scalar_one()
            )
            public_enum_count = int(
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
            has_alembic_version = bool(
                connection.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM pg_catalog.pg_class AS c
                            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                            WHERE n.nspname = 'public'
                              AND c.relname = 'alembic_version'
                              AND c.relkind IN ('r', 'p')
                        )
                        """
                    )
                ).scalar_one()
            )
            revisions = (
                list(
                    connection.execute(
                        text("SELECT version_num FROM public.alembic_version ORDER BY version_num")
                    ).scalars()
                )
                if has_alembic_version
                else []
            )
    except Exception as exc:
        raise RuntimeError(
            "Read-only candidate-state check failed. Verify that the explicitly named local candidate database exists; connection details were withheld."
        ) from exc
    finally:
        engine.dispose()

    object_counts = {
        "relations": relation_count,
        "custom_types": custom_type_count,
        "routines": routine_count,
        "extensions": extension_count,
        "extra_schemas": extra_schema_count,
    }
    return {
        "server_version": server_version,
        "server_encoding": server_encoding,
        "empty": not any(object_counts.values()),
        "object_counts": object_counts,
        "public_table_count_including_alembic_version": public_table_count,
        "public_enum_count": public_enum_count,
        "revisions": revisions,
    }


def _validate_alembic_registration() -> dict[str, Any]:
    if not ALEMBIC_CONFIG_PATH.is_file():
        raise FileNotFoundError("The isolated H3 candidate alembic.ini is missing.")
    config = Config(str(ALEMBIC_CONFIG_PATH))
    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions())
    head = script.get_current_head()
    if len(revisions) != 1 or head != builder.CANDIDATE_REVISION:
        raise ValueError(
            "The isolated candidate Alembic directory must contain exactly the approved single root revision."
        )
    return {"registered_head": head, "revision_count": len(revisions)}


def _source_preflight() -> dict[str, Any]:
    source_url = _resolve_source_url()
    return builder._source_preflight(source_url)


def _apply_with_alembic(candidate_url: URL, candidate_database: str) -> None:
    previous_url = os.environ.get("H3_CANDIDATE_DATABASE_URL")
    previous_name = os.environ.get("H3_CANDIDATE_DATABASE_NAME")
    os.environ["H3_CANDIDATE_DATABASE_URL"] = candidate_url.render_as_string(hide_password=False)
    os.environ["H3_CANDIDATE_DATABASE_NAME"] = candidate_database
    try:
        config = Config(str(ALEMBIC_CONFIG_PATH))
        command.upgrade(config, "head")
    except Exception as exc:
        # Do not print Alembic/driver tracebacks here; they can contain connection details.
        raise RuntimeError(
            f"Alembic candidate application failed ({type(exc).__name__}). Preserve this database; the script never drops or resets it."
        ) from exc
    finally:
        if previous_url is None:
            os.environ.pop("H3_CANDIDATE_DATABASE_URL", None)
        else:
            os.environ["H3_CANDIDATE_DATABASE_URL"] = previous_url
        if previous_name is None:
            os.environ.pop("H3_CANDIDATE_DATABASE_NAME", None)
        else:
            os.environ["H3_CANDIDATE_DATABASE_NAME"] = previous_name


def run(candidate_database: str, action: str) -> dict[str, Any]:
    candidate_database = validate_candidate_database_name(candidate_database)
    candidate_artifact = load_and_validate_candidate()
    alembic_registration = _validate_alembic_registration()
    source = _source_preflight()
    candidate_url = _resolve_candidate_url(candidate_database)

    report: dict[str, Any] = {
        "action": action,
        "source_database": builder.APPROVED_SOURCE_DATABASE,
        "source_revision": builder.APPROVED_SOURCE_REVISION,
        "source_server_version": source["server_version"],
        "candidate_database": candidate_database,
        "candidate_revision": candidate_artifact["revision"],
        "candidate_schema_sql_sha256": candidate_artifact["schema_sql_sha256"],
        "candidate_schema_sql_bytes": candidate_artifact["schema_sql_bytes"],
        "alembic_registration": alembic_registration,
        "protected_databases_contacted": False,
        "protected_databases_modified": False,
    }

    if action == "create-database":
        if _database_exists(candidate_url):
            raise ValueError(
                "Candidate database already exists. Nothing was dropped or modified; inspect it or choose a new approved disposable name."
            )
        server_state = _maintenance_server_state(candidate_url)
        if server_state != {
            "server_version": source["server_version"],
            "server_encoding": source["server_encoding"],
        }:
            raise ValueError(
                "Candidate PostgreSQL server version/encoding must exactly match the approved H2-prime source; no database was created."
            )
        source_encoding = str(source["server_encoding"])
        _create_candidate_database(candidate_url, source_encoding)
        state = _state(candidate_url)
        if not POSTGRESQL_18_4_PATTERN.match(state["server_version"]):
            raise RuntimeError(
                "Candidate database was created, but the local PostgreSQL server is not version 18.4. Preserve the empty disposable database and stop."
            )
        if not state["empty"]:
            raise RuntimeError(
                "New candidate database is not empty. It was not reset or dropped; preserve it and investigate."
            )
        report.update({"gate": "CREATE_DATABASE_PASS", "candidate_database_created": True, "candidate_state": state})
        return report

    if not _database_exists(candidate_url):
        if action == "dry-run":
            report.update(
                {
                    "gate": "DRY_RUN_READY",
                    "candidate_database_exists": False,
                    "next_step": "Create only this approved disposable database with --create-database, then repeat --dry-run.",
                }
            )
            return report
        raise ValueError("Candidate database does not exist. Run the explicit --create-database action first.")

    state = _state(candidate_url)
    report.update({"candidate_database_exists": True, "candidate_state": state})
    if state["server_version"] != source["server_version"] or state["server_encoding"] != source["server_encoding"]:
        raise ValueError(
            "Candidate PostgreSQL version/encoding does not exactly match the approved H2-prime source. No candidate migration was applied."
        )
    if not POSTGRESQL_18_4_PATTERN.match(state["server_version"]):
        raise ValueError(
            f"H3-A verification target is PostgreSQL 18.4; observed {state['server_version']!r}. No candidate migration was applied."
        )

    if action == "dry-run":
        if state["empty"]:
            report.update(
                {
                    "gate": "DRY_RUN_READY",
                    "next_step": "Review the report, then rerun with --apply to apply the static candidate only to this empty disposable database.",
                }
            )
            return report
        if state["revisions"] == [builder.CANDIDATE_REVISION]:
            report.update(
                {
                    "gate": "DRY_RUN_ALREADY_APPLIED",
                    "next_step": "Run the read-only schema comparison; do not apply the candidate again.",
                }
            )
            return report
        raise ValueError(
            "Candidate database is not empty and is not at the single expected H3 candidate revision. It was not changed."
        )

    if action != "apply":
        raise ValueError("Unsupported H3 candidate action.")

    if not state["empty"]:
        raise ValueError(
            "Refusing to apply to a non-empty database. No objects were dropped or modified; preserve it and choose a fresh approved disposable database."
        )

    _apply_with_alembic(candidate_url, candidate_database)
    final_state = _state(candidate_url)
    if final_state["revisions"] != [builder.CANDIDATE_REVISION]:
        raise RuntimeError(
            "Alembic returned, but the read-only post-apply check did not find exactly the candidate revision. Preserve the database for review."
        )
    if (
        final_state["public_table_count_including_alembic_version"] != builder.EXPECTED_PUBLIC_TABLES
        or final_state["public_enum_count"] != builder.EXPECTED_PUBLIC_ENUMS
    ):
        raise RuntimeError(
            "Alembic returned, but the read-only post-apply counts do not match the recorded source counts. Preserve the database and inspect the schema diff."
        )

    report.update(
        {
            "gate": "APPLY_PASS",
            "candidate_state_after_apply": final_state,
            "schema_parity": "NOT_YET_CHECKED",
            "next_step": "Run scripts.h3.compare_h3_candidate_schema in module mode; apply success is not schema-parity proof.",
        }
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely prepare or apply the isolated H3-A baseline to an approved local disposable PostgreSQL database."
    )
    parser.add_argument("--candidate-database", default="afcon360_h3_candidate_test")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--dry-run", action="store_true", help="Read-only preflight; this is the default.")
    actions.add_argument(
        "--create-database",
        action="store_true",
        help="Create only the named, approved disposable candidate database; never drops or resets a database.",
    )
    actions.add_argument(
        "--apply",
        action="store_true",
        help="Apply the static candidate through the isolated Alembic environment after empty-target checks.",
    )
    args = parser.parse_args(argv)
    action = "create-database" if args.create_database else "apply" if args.apply else "dry-run"
    try:
        report = run(args.candidate_database, action)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"H3 candidate {action} BLOCKED: {exc} Protected databases were not modified.")
        return 2
    except Exception as exc:
        print(
            f"H3 candidate {action} BLOCKED: {type(exc).__name__}. "
            "No protected database was targeted; no database was dropped or reset."
        )
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
