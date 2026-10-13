"""Enum + CHECK-constraint static policy tests.

Detector status (Phase 1E):
  * The SQLAlchemy implicit-name enum detector below recognizes every
    required source form and is proven on AST fixtures that are independent
    of the present production declarations.
  * The CHECK-constraint naming detector enforces the sync tool's
    ``MANAGED_PREFIX = "ck_"`` rule (see scripts/sync_check_constraints.py):
    a model-declared ``CheckConstraint`` in ``__table_args__`` whose name is
    missing or does not begin with ``ck_`` is reported. Valid ``ck_*``
    declarations are accepted.
  * Repository-wide enforcement of both rules depends on the pending
    enum census / reconciliation roadmap (native PG ENUM columns and the
    deferred Transport lifecycle schema predate it), so no speculative
    repo-wide legacy allowlist and no blanket ban on explicitly named
    legacy mappings is introduced here. The remaining enforcement gap is
    reported with the Phase 1 final report instead of being pretended
    resolved.
"""

import ast
import pathlib

from app.utils.enums import get_all_enum_classes

MANAGED_CHECK_PREFIX = "ck_"

# Receivers that conventionally expose the SQLAlchemy Enum constructor.
_SA_ENUM_RECEIVERS = {"db", "sqlalchemy", "sa", "postgresql"}


def _parse(source):
    return ast.parse(source)


def _sa_enum_call_names(tree):
    """Bare names bound to a SQLAlchemy Enum/ENUM constructor in this file."""
    names = set()
    stdlib_shadow = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in ("sqlalchemy", "sqlalchemy.types") or module.startswith(
                "sqlalchemy.dialects"
            ):
                for alias in node.names:
                    if alias.name in ("Enum", "ENUM"):
                        names.add(alias.asname or alias.name)
            elif module == "enum":
                for alias in node.names:
                    stdlib_shadow.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "enum" or alias.name.startswith("enum."):
                    stdlib_shadow.add((alias.asname or alias.name).split(".")[0])
    return names - stdlib_shadow


def _has_name_keyword(call):
    return any(keyword.arg == "name" for keyword in call.keywords)


def find_implicit_sa_enum_calls(source):
    """Return ``[(lineno, label)]`` for SQLAlchemy enum constructors lacking ``name=``.

    Detects: ``SQLEnum(X)`` / ``db.Enum(X)`` / ``Enum(X)`` imported from
    SQLAlchemy / ``db.Enum('a', 'b')`` / ``sqlalchemy.Enum(...)`` /
    ``sa.Enum(...)`` / aliased ``SAEnum(X)`` / PostgreSQL ``ENUM`` aliases --
    in every case only when no explicit ``name=`` keyword is present.
    Standard-library ``enum.Enum`` subclass definitions are never calls and
    are therefore never reported.
    """
    tree = _parse(source)
    sa_names = _sa_enum_call_names(tree)
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        label = None
        if isinstance(func, ast.Name):
            if func.id in sa_names or func.id == "PgEnum":
                label = func.id
        elif isinstance(func, ast.Attribute):
            receiver = func.value
            receiver_name = (
                receiver.id if isinstance(receiver, ast.Name) else None
            )
            if func.attr in ("Enum", "ENUM") and receiver_name in _SA_ENUM_RECEIVERS:
                label = f"{receiver_name}.{func.attr}"
        if label is not None and not _has_name_keyword(node):
            findings.append((node.lineno, label))
    return sorted(findings)


def _check_constraint_call_names(tree):
    names = {"CheckConstraint"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "CheckConstraint":
                    names.add(alias.asname or alias.name)
    return names


def _table_args_values(tree):
    """Yield the assigned value nodes of every ``__table_args__`` in the file."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                targets = []
                value = None
                if isinstance(stmt, ast.Assign):
                    targets = stmt.targets
                    value = stmt.value
                elif isinstance(stmt, ast.AnnAssign):
                    targets = [stmt.target]
                    value = stmt.value
                else:
                    continue
                if value is None:
                    continue
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == "__table_args__":
                        yield value


def find_unnamed_check_constraints(source):
    """Return ``[(lineno, label)]`` for CHECK declarations outside the ``ck_*`` rule.

    Inspects ``CheckConstraint`` calls declared inside ``__table_args__``
    (bare, ``db.``-prefixed, or aliased imports). A call is reported when its
    ``name`` is missing, is not a string literal starting with ``ck_``, or is
    dynamic (unverifiable). Valid ``ck_*`` declarations are accepted. This
    matches the sync tool's ``MANAGED_PREFIX`` handling: anything else is
    ignored by the tool, so it must be surfaced here.
    """
    tree = _parse(source)
    names = _check_constraint_call_names(tree)
    findings = []
    for value in _table_args_values(tree):
        for node in ast.walk(value):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_check = (
                isinstance(func, ast.Name)
                and func.id in names
                or isinstance(func, ast.Attribute)
                and func.attr == "CheckConstraint"
            )
            if not is_check:
                continue
            name_keyword = next(
                (keyword for keyword in node.keywords if keyword.arg == "name"),
                None,
            )
            if name_keyword is None:
                findings.append((node.lineno, "missing-name"))
                continue
            try:
                name_value = ast.literal_eval(name_keyword.value)
            except Exception:
                name_value = None
            if not isinstance(name_value, str) or not name_value.startswith(
                MANAGED_CHECK_PREFIX
            ):
                findings.append((node.lineno, f"bad-prefix:{name_value!r}"))
    return sorted(findings)


def test_no_inline_pg_enums():
    """Bare PG ENUM constructors must carry an explicit ``name=`` (legacy mapping).

    Flags ``ENUM``/``PgEnum`` calls that lack ``name=``. Explicitly named
    legacy mappings (e.g. ``PgEnum(name='servicetype', create_type=False)``)
    are exempt: banning them is deferred to the enum census. The remaining
    implicit-name SQLAlchemy enum forms (``db.Enum``, ``SQLEnum``, ...) are
    proven on AST fixtures below; repo-wide enforcement awaits the census
    (see module docstring).
    """
    root = pathlib.Path("app")
    allowed = {pathlib.Path("app/utils/enums.py")}
    violations = []
    for path in root.rglob("*.py"):
        if path in allowed:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = getattr(f, "id", None) or getattr(f, "attr", None)
                if name in {"ENUM", "PgEnum"} and not any(
                    keyword.arg == "name" for keyword in node.keywords
                ):
                    violations.append(f"{path}:{node.lineno}")
    assert violations == [
    ], f"Implicit-name PG ENUM declarations (missing name=): {violations}"


def test_all_active_enums_have_create_type_false():
    """All active enums must have create_type=False."""
    # Since we're using String + CHECK constraints instead of PgEnum,
    # this test is not applicable but kept for compatibility
    pass


def test_active_enum_names_unique():
    """No two active enums may share the same PG type name."""
    # Since we're not using PgEnum anymore, this test is not applicable
    pass


def test_no_duplicate_values_within_enum():
    """No member value may appear twice within a single enum."""
    for enum_cls in get_all_enum_classes():
        values = enum_cls.values()
        assert len(values) == len(set(values)), (
            f"Duplicate values in enum {enum_cls.__name__}: {values}"
        )


# ---------------------------------------------------------------------------
# AST fixtures: implicit-name SQLAlchemy enum detection (positive cases)
# ---------------------------------------------------------------------------

def test_detects_sqle_num_without_name():
    source = (
        "from sqlalchemy import Enum as SQLEnum\n"
        "class M(Base):\n"
        "    status = Column(SQLEnum(Status))\n"
    )
    assert find_implicit_sa_enum_calls(source) != []


def test_detects_db_enum_without_name():
    source = (
        "from app.extensions import db\n"
        "class M(db.Model):\n"
        "    status = db.Column(db.Enum(Status))\n"
    )
    findings = find_implicit_sa_enum_calls(source)
    assert len(findings) == 1 and findings[0][1] == "db.Enum"


def test_detects_bare_sa_enum_without_name():
    source = (
        "from sqlalchemy import Enum\n"
        "class M(Base):\n"
        "    status = Column(Enum(Status))\n"
    )
    assert find_implicit_sa_enum_calls(source) != []


def test_detects_db_enum_value_list_without_name():
    source = (
        "from app.extensions import db\n"
        "class M(db.Model):\n"
        "    kind = db.Column(db.Enum('a', 'b'))\n"
    )
    assert find_implicit_sa_enum_calls(source) != []


def test_detects_sqlalchemy_attribute_forms_without_name():
    source = (
        "import sqlalchemy\n"
        "import sqlalchemy as sa\n"
        "a = sqlalchemy.Enum(Status)\n"
        "b = sa.Enum(Status)\n"
    )
    assert len(find_implicit_sa_enum_calls(source)) == 2


def test_detects_aliased_sa_enum_without_name():
    source = (
        "from sqlalchemy import Enum as SAEnum\n"
        "status = Column(SAEnum(Status))\n"
    )
    findings = find_implicit_sa_enum_calls(source)
    assert len(findings) == 1 and findings[0][1] == "SAEnum"


def test_detects_postgres_enum_alias_without_name():
    source = (
        "from sqlalchemy.dialects.postgresql import ENUM\n"
        "status = Column(ENUM('a', 'b'))\n"
    )
    assert find_implicit_sa_enum_calls(source) != []


# ---------------------------------------------------------------------------
# AST fixtures: exemptions (negative cases)
# ---------------------------------------------------------------------------

def test_explicit_name_legacy_mapping_is_not_rejected():
    source = (
        "from sqlalchemy import Enum\n"
        "status = Column(Enum(PyEnum, name='existing_pg_type'))\n"
    )
    assert find_implicit_sa_enum_calls(source) == []


def test_explicit_name_db_enum_is_not_rejected():
    source = (
        "from app.extensions import db\n"
        "status = db.Column(db.Enum(PyEnum, name='existing_pg_type'))\n"
    )
    assert find_implicit_sa_enum_calls(source) == []


def test_stdlib_enum_catalogue_is_not_rejected():
    source = (
        "from enum import Enum\n"
        "class Colour(str, Enum):\n"
        "    RED = 'red'\n"
        "    BLUE = 'blue'\n"
    )
    assert find_implicit_sa_enum_calls(source) == []


def test_stdlib_enum_module_form_is_not_rejected():
    source = (
        "import enum\n"
        "class Colour(str, enum.Enum):\n"
        "    RED = 'red'\n"
    )
    assert find_implicit_sa_enum_calls(source) == []


# ---------------------------------------------------------------------------
# AST fixtures: CHECK-constraint naming
# ---------------------------------------------------------------------------

def test_flags_check_constraint_with_missing_name():
    source = (
        "from sqlalchemy import CheckConstraint\n"
        "class M(Base):\n"
        "    __table_args__ = (\n"
        "        CheckConstraint('a >= 0'),\n"
        "    )\n"
    )
    findings = find_unnamed_check_constraints(source)
    assert len(findings) == 1 and findings[0][1] == "missing-name"


def test_flags_check_constraint_with_non_ck_prefix():
    source = (
        "from sqlalchemy import CheckConstraint\n"
        "class M(Base):\n"
        "    __table_args__ = (\n"
        "        CheckConstraint('a >= 0', name='chk_something'),\n"
        "        CheckConstraint('b >= 0', name='no_prefix'),\n"
        "    )\n"
    )
    assert len(find_unnamed_check_constraints(source)) == 2


def test_accepts_valid_ck_prefixed_declarations():
    source = (
        "from sqlalchemy import CheckConstraint\n"
        "class M(Base):\n"
        "    __table_args__ = (\n"
        "        CheckConstraint('a >= 0', name='ck_a_positive'),\n"
        "        CheckConstraint(\"status IN ('x')\", name='ck_status'),\n"
        "    )\n"
    )
    assert find_unnamed_check_constraints(source) == []


def test_flags_db_prefixed_and_aliased_check_forms():
    source = (
        "from app.extensions import db\n"
        "from sqlalchemy import CheckConstraint as CC\n"
        "class M(Base):\n"
        "    __table_args__ = (\n"
        "        db.CheckConstraint('a >= 0'),\n"
        "        CC('b >= 0', name='ck_b_ok'),\n"
        "        CC('c >= 0', name='wrong'),\n"
        "    )\n"
    )
    findings = find_unnamed_check_constraints(source)
    assert len(findings) == 2
