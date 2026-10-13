"""Regression proof for Phase 1C: enum CHECK-constraint helper audit.

Verifies the generated SQL expressions directly against the real mapped
column names. No migration runs, no constraint is created in any database,
and no database connection is opened (table metadata only).
"""

import re

from app.utils.enums import OrgChangeSource, OrgVerificationStatus, get_all_enum_classes


def _table_check_sql(model_cls, constraint_name):
    table = model_cls.__table__
    for constraint in table.constraints:
        if getattr(constraint, "name", None) == constraint_name:
            return str(constraint.sqltext)
    raise AssertionError(
        f"{constraint_name} not found on {table.name}: "
        f"{sorted(str(getattr(c, 'name', None)) for c in table.constraints)}"
    )


def test_org_change_source_targets_source_column():
    from app.identity.models.licence_document import OrganisationAuditLog

    assert "source" in {c.name for c in OrganisationAuditLog.__table__.columns}
    assert "change_source" not in {
        c.name for c in OrganisationAuditLog.__table__.columns
    }
    expr = OrgChangeSource.check_constraint()
    assert expr == "source IN ('system', 'user', 'admin')"
    assert "change_source" not in expr
    table_sql = _table_check_sql(OrganisationAuditLog, "ck_org_change_source")
    assert table_sql.startswith("source IN (")


def test_organisation_verification_status_targets_status_column():
    from app.identity.models.kyb import OrganisationVerification

    columns = {c.name for c in OrganisationVerification.__table__.columns}
    assert "status" in columns
    assert "verification_status" not in columns
    table_sql = _table_check_sql(
        OrganisationVerification, "ck_org_verification_status"
    )
    assert table_sql.startswith("status IN ("), table_sql
    for value in OrgVerificationStatus.values():
        assert f"'{value}'" in table_sql


def test_organisation_helpers_match_organisation_columns():
    from app.identity.models.organisation import Organisation

    columns = {c.name for c in Organisation.__table__.columns}
    assert "verification_status" in columns
    assert "lifecycle_state" in columns
    verification_sql = _table_check_sql(
        Organisation, "ck_org_verification_status"
    )
    assert verification_sql.startswith("verification_status IN ("), verification_sql
    lifecycle_sql = _table_check_sql(Organisation, "ck_org_lifecycle_state")
    assert lifecycle_sql.startswith("lifecycle_state IN ("), lifecycle_sql


def test_all_helpers_emit_sane_single_column_in_expressions():
    pattern = re.compile(r"^[a-z_][a-z0-9_]* IN \('[^']*'(?:, '[^']*')*\)$")
    for enum_cls in get_all_enum_classes():
        expr = enum_cls.check_constraint()
        assert pattern.match(expr), f"{enum_cls.__name__}: {expr!r}"
        for value in enum_cls.values():
            assert f"'{value}'" in expr, f"{enum_cls.__name__} missing {value!r}"
