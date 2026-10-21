"""Pure tests for enum_query.py target-safety validation; no PostgreSQL connection."""
from __future__ import annotations

import pytest

from enum_query import validate_local_test_dsn


def test_local_dedicated_test_dsn_is_accepted() -> None:
    dsn = "postgresql://test_user:placeholder@localhost:5432/afcon360_test"
    assert validate_local_test_dsn(dsn) == dsn


def test_sqlalchemy_psycopg2_scheme_is_normalized() -> None:
    dsn = "postgresql+psycopg2://test_user:placeholder@127.0.0.1:5432/afcon360_test"
    assert validate_local_test_dsn(dsn) == (
        "postgresql://test_user:placeholder@127.0.0.1:5432/afcon360_test"
    )


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://test_user:placeholder@db.example.com:5432/afcon360_test",
        "postgresql://test_user:placeholder@localhost:5432/afcon360_prod",
        "sqlite:///afcon360_test",
        "postgresql:///afcon360_test",
    ],
)
def test_unsafe_or_ambiguous_target_is_rejected(dsn: str) -> None:
    with pytest.raises(ValueError):
        validate_local_test_dsn(dsn)
