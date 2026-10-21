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

COMPARE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "h3"
    / "compare_h3_candidate_schema.py"
)
COMPARE_SPEC = importlib.util.spec_from_file_location("h3_candidate_schema_compare", COMPARE_PATH)
assert COMPARE_SPEC is not None and COMPARE_SPEC.loader is not None
comparer = importlib.util.module_from_spec(COMPARE_SPEC)
COMPARE_SPEC.loader.exec_module(comparer)


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
-- Name: example; Type: TABLE; Schema: public; Owner: first_owner
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
    assert "Owner: <normalized>" in sql
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
    assert builder.validate_schema_sql(sql, expected_tables=2, expected_enums=1, minimum_size=False) == {
        "table_ddl_count": 2,
        "enum_ddl_count": 1,
    }
    with pytest.raises(ValueError, match="table count mismatch"):
        builder.validate_schema_sql(sql, expected_tables=3, expected_enums=1, minimum_size=False)


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
    assert 'execution_options={"no_parameters": True}' in rendered
    assert "metadata.create_all" not in rendered
    assert "from app." not in rendered
    assert "a" * 64 in rendered
    compile(rendered, "<candidate-migration>", "exec")


def test_schema_comparison_passes_only_identical_normalized_sql():
    source = "CREATE TYPE public.example_status AS ENUM ('OPEN');\nCREATE TABLE public.example (id BIGINT);\n"
    same = comparer.compare_schema_texts(source, source)
    assert same["match"] is True
    assert same["difference_line_count"] == 0
    changed = comparer.compare_schema_texts(source, source.replace("id BIGINT", "id INTEGER"))
    assert changed["match"] is False
    assert changed["difference_line_count"] > 0
    assert any("INTEGER" in line for line in changed["diff_lines"])


def test_array_cast_normalization_converts_outer_cast_to_per_element():
    """Source form ((ARRAY[...])::text[]) normalizes to per-element form ANY (ARRAY[(...)::text, ...])."""
    source_line = (
        'CHECK (("reason")::"text" = ANY '
        '((ARRAY[\'booked\'::character varying, \'temporary_hold\'::character varying])::"text"[]))'
    )
    expected = (
        'CHECK (("reason")::"text" = ANY '
        '(ARRAY[(\'booked\'::character varying)::"text", (\'temporary_hold\'::character varying)::"text"]))'
    )
    normalized = builder.normalize_schema_dump(source_line).strip()
    assert expected == normalized


def test_array_cast_normalization_handles_escaped_apostrophes():
    """Values containing escaped apostrophes (SQL '' syntax) remain doubled after normalization."""
    source_line = "CHECK (status = ANY ((ARRAY['owner''s_block'::character varying, 'booked'::character varying])::\"text\"[]))"
    normalized = builder.normalize_schema_dump(source_line).strip()
    expected = 'CHECK (status = ANY (ARRAY[(\'owner\'\'s_block\'::character varying)::"text", (\'booked\'::character varying)::"text"]))'
    assert normalized == expected


def test_array_cast_normalization_handles_varchar_alias():
    """The varchar type alias is treated the same as character varying."""
    source_line = 'CHECK (status = ANY ((ARRAY[\'booked\'::varchar, \'pending\'::varchar])::"text"[]))'
    normalized = builder.normalize_schema_dump(source_line).strip()
    expected = 'CHECK (status = ANY (ARRAY[(\'booked\'::character varying)::"text", (\'pending\'::character varying)::"text"]))'
    assert normalized == expected


def test_array_cast_normalization_is_idempotent():
    """Applying normalization twice produces the same result (no double-wrapping)."""
    source_line = 'CHECK (status = ANY ((ARRAY[\'booked\'::character varying, \'pending\'::character varying])::"text"[]))'
    first = builder.normalize_schema_dump(source_line)
    second = builder.normalize_schema_dump(first)
    assert first == second, "Normalization must be idempotent"


def test_array_cast_normalization_preserves_already_canonical_form():
    """Lines already in per-element form are left unchanged."""
    canonical_line = 'CHECK (("reason")::"text" = ANY (ARRAY[(\'booked\'::character varying)::"text", (\'pending\'::character varying)::"text"]))'
    normalized = builder.normalize_schema_dump(canonical_line)
    assert normalized.strip() == canonical_line


def test_array_cast_normalization_does_not_affect_unrelated_expressions():
    """Non-matching expressions (non-text arrays, different casts) remain unchanged."""
    unrelated = [
        'CHECK (value = ANY (ARRAY[1, 2, 3]))',  # integer array
        'CHECK (value = ANY (ARRAY[\'a\'::text, \'b\'::text]))',  # text cast, not character varying
        'CHECK (value IN (\'a\', \'b\'))',  # IN syntax, not = ANY(ARRAY)
        'CREATE INDEX idx ON t (col) WHERE col = ANY (ARRAY[\'a\'::int, \'b\'::int])',  # int array in index
    ]
    for line in unrelated:
        normalized = builder.normalize_schema_dump(line)
        assert normalized.strip() == line, f"Unrelated expression changed: {line} -> {normalized}"
