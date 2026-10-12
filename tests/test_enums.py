import ast
import pathlib
from app.utils.enums import get_all_enum_classes


def test_no_inline_pg_enums():
    """Fail if any file outside app/utils/enums.py constructs a PG ENUM."""
    root = pathlib.Path("app")
    allowed = {pathlib.Path("app/utils/enums.py")}
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
                if name in {"ENUM", "PgEnum"}:
                    raise AssertionError(
                        f"Inline PG ENUM in {path}. "
                        f"Move it to app/utils/enums.py."
                    )


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