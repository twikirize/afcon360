"""Static contract: every SQLAlchemy DateTime model column is timezone-aware."""

import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _qualified_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _qualified_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _qualified_name(node.func)
    return ""


def _datetime_type_argument(call):
    """Find a DateTime type argument in Column()/mapped_column()."""
    args = list(call.args)
    if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
        args = args[1:]
    if not args:
        return None
    candidate = args[0]
    name = _qualified_name(candidate)
    if name.split(".")[-1] != "DateTime":
        return None
    return candidate


def _timezone_true(type_node):
    if not isinstance(type_node, ast.Call):
        return False
    if _qualified_name(type_node.func).split(".")[-1] != "DateTime":
        return False
    return any(
        keyword.arg == "timezone"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in type_node.keywords
    )


def test_all_sqlalchemy_datetime_model_columns_are_timezone_aware():
    violations = []

    for path in sorted(APP_ROOT.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            violations.append(f"{path.relative_to(APP_ROOT)}: unable to parse ({exc})")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func_name = _qualified_name(node.func).split(".")[-1]
            if func_name not in {"Column", "mapped_column"}:
                continue
            type_node = _datetime_type_argument(node)
            if type_node is None or _timezone_true(type_node):
                continue
            relative = path.relative_to(APP_ROOT).as_posix()
            violations.append(
                f"{relative}:{node.lineno}: {ast.get_source_segment(source, type_node)} "
                "must declare timezone=True"
            )

    assert not violations, (
        "Found naive SQLAlchemy DateTime columns. Calendar-only fields should "
        "use Date, and instant-valued fields must use DateTime(timezone=True):\n"
        + "\n".join(violations)
    )
