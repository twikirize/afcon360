"""Regression proof for Phase 1C, updated for Phase 4 restoration.

The enum CHECK helpers were audited in Phase 1; Phase 4 restores the
columns to native PostgreSQL ENUM references and removes the 28
model-only enum-domain CHECK declarations (none was ever installed in
either database). These tests now pin the restored contract:

- helper expressions still target the real columns;
- model columns use the intended native PG enum types;
- no stale enum-domain CHECK remains on the converted tables.

No migration runs and no database connection is opened (metadata only).
"""

import re

from sqlalchemy import inspect as sa_inspect

from app.utils.enums import OrgChangeSource, OrgVerificationStatus, get_all_enum_classes
from sqlalchemy.dialects.postgresql import ENUM as PgEnum


def _table_of(model_cls):
    # sqlalchemy.inspect() is the public, typed entry point to a mapped
    # class's Table; direct __table__ access is invisible to checkers.
    return sa_inspect(model_cls).local_table


def _table_check_names(model_cls):
    return sorted(
        str(getattr(c, "name", None)) for c in _table_of(model_cls).constraints
    )


def _column_enum_type(model_cls, column_name):
    return _table_of(model_cls).c[column_name].type


def test_org_change_source_targets_source_column():
    from app.identity.models.licence_document import OrganisationAuditLog

    assert "source" in {c.name for c in _table_of(OrganisationAuditLog).columns}
    assert "change_source" not in {
        c.name for c in _table_of(OrganisationAuditLog).columns
    }
    expr = OrgChangeSource.check_constraint()
    assert expr == "source IN ('system', 'user', 'admin')"
    assert "change_source" not in expr
    col_type = _column_enum_type(OrganisationAuditLog, "source")
    assert isinstance(col_type, PgEnum)
    assert col_type.name == "org_change_source"
    assert "ck_org_change_source" not in _table_check_names(OrganisationAuditLog)


def test_organisation_verification_status_targets_status_column():
    from app.identity.models.kyb import OrganisationVerification

    columns = {c.name for c in _table_of(OrganisationVerification).columns}
    assert "status" in columns
    assert "verification_status" not in columns
    col_type = _column_enum_type(OrganisationVerification, "status")
    assert isinstance(col_type, PgEnum)
    assert col_type.name == "org_verification_status"
    assert "ck_org_verification_status" not in _table_check_names(
        OrganisationVerification
    )
    for value in OrgVerificationStatus.values():
        assert value in (col_type.enums or [])


def test_organisation_helpers_match_organisation_columns():
    from app.identity.models.organisation import Organisation

    columns = {c.name for c in _table_of(Organisation).columns}
    assert "verification_status" in columns
    assert "lifecycle_state" in columns
    verification_type = _column_enum_type(Organisation, "verification_status")
    assert isinstance(verification_type, PgEnum)
    assert verification_type.name == "org_verification_status"
    lifecycle_type = _column_enum_type(Organisation, "lifecycle_state")
    assert isinstance(lifecycle_type, PgEnum)
    assert lifecycle_type.name == "org_lifecycle_state"
    names = _table_check_names(Organisation)
    assert "ck_org_verification_status" not in names
    assert "ck_org_lifecycle_state" not in names


def test_all_helpers_emit_sane_single_column_in_expressions():
    pattern = re.compile(r"^[a-z_][a-z0-9_]* IN \('[^']*'(?:, '[^']*')*\)$")
    for enum_cls in get_all_enum_classes():
        expr = enum_cls.check_constraint()
        assert pattern.match(expr), f"{enum_cls.__name__}: {expr!r}"
        for value in enum_cls.values():
            assert f"'{value}'" in expr, f"{enum_cls.__name__} missing {value!r}"
