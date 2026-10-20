from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "h3"
    / "build_h3_candidate.py"
)
SPEC = importlib.util.spec_from_file_location("h3_candidate_builder", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def test_source_identity_accepts_only_approved_disposable_h2_prime_state():
    builder.validate_source_identity(
        database=builder.APPROVED_SOURCE_DATABASE,
        revision=builder.APPROVED_SOURCE_REVISION,
        server_version="18.4",
    )


def test_source_identity_rejects_production_or_an_unapproved_revision():
    with pytest.raises(ValueError):
        builder.validate_source_identity(
            database="afcon360_prod",
            revision=builder.APPROVED_SOURCE_REVISION,
            server_version="18.4",
        )
    with pytest.raises(ValueError):
        builder.validate_source_identity(
            database=builder.APPROVED_SOURCE_DATABASE,
            revision="unknown_revision",
            server_version="18.4",
        )


def test_dump_normalization_removes_psql_wrappers_and_default_public_schema_setup():
    dump = r'''-- PostgreSQL database dump
-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4
\restrict abc123
SET statement_timeout = 0;
CREATE SCHEMA public;
ALTER SCHEMA public OWNER TO pg_database_owner;
CREATE TYPE public.example_status AS ENUM ('OPEN', 'CLOSED');
CREATE TABLE public.example (id BIGINT NOT NULL);
\unrestrict abc123
-- PostgreSQL database dump complete
'''
    sql = builder.normalize_schema_dump(dump)
    assert "\\restrict" not in sql
    assert "\\unrestrict" not in sql
    assert "CREATE SCHEMA public" not in sql
    assert "ALTER SCHEMA public OWNER" not in sql
    assert "CREATE TYPE public.example_status AS ENUM" in sql
    assert "CREATE TABLE public.example" in sql


def test_dump_normalization_rejects_unknown_psql_meta_commands():
    with pytest.raises(ValueError, match="psql-only command"):
        builder.normalize_schema_dump("\\connect afcon360_prod\n")


def test_schema_validator_requires_exact_table_and_enum_counts():
    sql = (
        "CREATE TYPE public.example_status AS ENUM ('OPEN', 'CLOSED');\n"
        "CREATE TABLE public.example (id BIGINT NOT NULL);\n"
        "CREATE TABLE public.example_history (id BIGINT NOT NULL);\n"
    )
    assert builder.validate_schema_sql(sql, expected_tables=2, expected_enums=1) == {
        "table_ddl_count": 2,
        "enum_ddl_count": 1,
    }
    with pytest.raises(ValueError, match="table count mismatch"):
        builder.validate_schema_sql(sql, expected_tables=3, expected_enums=1)


def test_schema_validator_rejects_alembic_version_and_data_copy():
    with pytest.raises(ValueError, match="alembic_version"):
        builder.validate_schema_sql(
            "CREATE TABLE public.alembic_version (version_num VARCHAR(32));",
            expected_tables=1,
            expected_enums=0,
        )
    with pytest.raises(ValueError, match="COPY commands"):
        builder.validate_schema_sql(
            "CREATE TYPE public.example_status AS ENUM ('OPEN');\n"
            "CREATE TABLE public.example (id BIGINT);\n"
            "COPY public.example (id) FROM stdin;\n1\n\\.\n",
            expected_tables=1,
            expected_enums=1,
        )


def test_candidate_is_static_and_not_derived_from_runtime_models():
    sql = "CREATE TYPE public.example_status AS ENUM ('OPEN');\nCREATE TABLE public.example (id BIGINT);\n"
    rendered = builder.render_candidate_migration(
        sql,
        server_version="18.4",
        pg_dump_version="18.4",
        source_sha256="a" * 64,
    )
    assert "revision = 'h3a20261020'" in rendered
    assert "down_revision = None" in rendered
    assert "exec_driver_sql(_SCHEMA_SQL)" in rendered
    assert "metadata.create_all" not in rendered
    assert "from app." not in rendered
    assert "a" * 64 in rendered
    compile(rendered, "<candidate-migration>", "exec")
