from __future__ import annotations

import hashlib

import pytest

from scripts.h3 import apply_h3_candidate as applier
from scripts.h3 import build_h3_candidate as builder


def test_candidate_database_allowlist_accepts_only_disposable_names():
    assert applier.validate_candidate_database_name("afcon360_h3_candidate_test")
    assert applier.validate_candidate_database_name("afcon360_h3_candidate_v1_test")
    assert applier.validate_candidate_database_name("afcon360_h3_candidate_replay-2_test")

    for unsafe in (
        "afcon360_prod",
        "afcon360_test",
        "afcon360_h2p_replay_20261018_test",
        "afcon360_h3_candidate",
        "AFCON360_H3_CANDIDATE_TEST",
        "afcon360_h3_candidate_test; DROP DATABASE afcon360_prod",
    ):
        with pytest.raises(ValueError, match="afcon360_h3_candidate"):
            applier.validate_candidate_database_name(unsafe)


def test_h3a_candidate_integrity_checks_embedded_sql_hash(tmp_path):
    sql = (
        "CREATE TYPE public.example_status AS ENUM ('OPEN');\n"
        "CREATE TABLE public.example (id BIGINT NOT NULL);\n"
    )
    digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    rendered = builder.render_candidate_migration(
        sql,
        server_version="18.4",
        pg_dump_version="18.4",
        source_sha256=digest,
    )
    candidate_path = tmp_path / "candidate.py"
    candidate_path.write_text(rendered, encoding="utf-8", newline="\n")

    report = applier.load_and_validate_candidate(candidate_path, expected_sha256=digest)
    assert report["revision"] == "h3a20261020"
    assert report["down_revision"] is None
    assert report["schema_sql_sha256"] == digest
    assert report["schema_sql_bytes"] == len(sql.encode("utf-8"))


def test_h3a_candidate_integrity_check_rejects_sql_changed_after_generation(tmp_path):
    sql = (
        "CREATE TYPE public.example_status AS ENUM ('OPEN');\n"
        "CREATE TABLE public.example (id BIGINT NOT NULL);\n"
    )
    digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    rendered = builder.render_candidate_migration(
        sql,
        server_version="18.4",
        pg_dump_version="18.4",
        source_sha256=digest,
    )
    candidate_path = tmp_path / "tampered_candidate.py"
    candidate_path.write_text(rendered.replace("id BIGINT", "id INTEGER"), encoding="utf-8")

    with pytest.raises(ValueError, match="hash does not match"):
        applier.load_and_validate_candidate(candidate_path, expected_sha256=digest)


def test_h3a_candidate_integrity_check_rejects_non_root_revision(tmp_path):
    sql = "CREATE TABLE public.example (id BIGINT NOT NULL);\n"
    digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    rendered = builder.render_candidate_migration(
        sql,
        server_version="18.4",
        pg_dump_version="18.4",
        source_sha256=digest,
    )
    candidate_path = tmp_path / "wrong_revision.py"
    candidate_path.write_text(
        rendered.replace("revision = 'h3a20261020'", "revision = 'other_revision'"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="revision"):
        applier.load_and_validate_candidate(candidate_path, expected_sha256=digest)


def test_h3a_replay_version_gate_is_18_4_for_this_checkpoint():
    assert applier.POSTGRESQL_18_4_PATTERN.match("18.4")
    assert applier.POSTGRESQL_18_4_PATTERN.match("18.4 (Windows)")
    assert not applier.POSTGRESQL_18_4_PATTERN.match("18.6")
    assert not applier.POSTGRESQL_18_4_PATTERN.match("15.8")


def test_h3a_application_module_import_uses_supported_package_entrypoint():
    # The CLI is intended to run as a module from the repository root.
    assert callable(applier.main)
    assert applier.CANDIDATE_DATABASE_PATTERN.fullmatch("afcon360_h3_candidate_test")
