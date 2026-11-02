"""Executable checks for the PostgreSQL and SQLAlchemy-only test contract."""

import ast
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.config import TestingConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _python_files(directory: Path, pattern: str):
    return sorted(directory.rglob(pattern))


def _unsafe_sql_interpolation_nodes(path: Path):
    """Find SQL passed to SQLAlchemy through untrusted or dynamic interpolation.

    Static text() statements with bound parameters are valid PostgreSQL usage
    (for example transaction-scoped GUCs and advisory locks). The contract
    forbids interpolating request/runtime values into SQL strings; fixed
    module constants remain allowed for SQL identifiers.
    """
    tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))

    def has_untrusted_interpolation(expression):
        if isinstance(expression, ast.JoinedStr):
            for part in expression.values:
                if isinstance(part, ast.FormattedValue):
                    value = part.value
                    if not (isinstance(value, ast.Name) and value.id.isupper()):
                        return True
        if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
            return True
        if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute):
            if expression.func.attr == "format":
                return True
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "text" and node.args and has_untrusted_interpolation(node.args[0]):
                yield node
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "execute" and node.args and has_untrusted_interpolation(node.args[0]):
                yield node


@pytest.mark.no_database
def test_testing_config_is_dedicated_postgresql():
    url = make_url(str(TestingConfig.SQLALCHEMY_DATABASE_URI))
    assert url.get_backend_name() == 'postgresql'
    assert url.database and url.database.endswith('_test')


@pytest.mark.no_database
def test_testing_environment_selects_testing_config():
    source = (PROJECT_ROOT / 'app' / '__init__.py').read_text(encoding='utf-8-sig')
    assert "os.getenv('FLASK_ENV') == 'testing'" in source
    assert 'config_object = TestingConfig' in source


@pytest.mark.no_database
def test_application_and_pytest_code_do_not_embed_sql_text():
    files = _python_files(PROJECT_ROOT / 'app', '*.py')
    files.extend(PROJECT_ROOT.glob('*test*.py'))
    files.extend(_python_files(PROJECT_ROOT / 'scripts', 'test*.py'))
    files.extend(
        path for path in _python_files(PROJECT_ROOT / 'tests', '*.py')
        if path != Path(__file__)
    )
    files.append(PROJECT_ROOT / 'tests' / 'conftest.py')

    violations = [
        f'{path}:{node.lineno}'
        for path in files
        for node in _unsafe_sql_interpolation_nodes(path)
    ]
    assert not violations, 'Do not interpolate runtime values into SQL strings: ' + ', '.join(violations)


@pytest.mark.no_database
def test_pytest_code_does_not_use_sqlite_or_schema_ddl():
    files = list(PROJECT_ROOT.glob('*test*.py'))
    files.extend(_python_files(PROJECT_ROOT / 'scripts', 'test*.py'))
    files.extend([
        path for path in _python_files(PROJECT_ROOT / 'tests', '*.py')
        if path != Path(__file__)
    ])
    files.append(PROJECT_ROOT / 'tests' / 'conftest.py')
    violations = []

    for path in files:
        source = path.read_text(encoding='utf-8-sig')
        if 'sqlite://' in source.lower() and path.name != 'test_enum_query_guard.py':
            violations.append(f'{path}:sqlite')
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {'create_all', 'drop_all'}:
                    violations.append(f'{path}:{node.lineno}:{node.func.attr}')

    # This fixture deliberately mentions SQLite only to verify the production
    # guard rejects it; it must never be used as a test database.
    negative_guard = (PROJECT_ROOT / 'tests' / 'test_enum_query_guard.py').read_text(
        encoding='utf-8-sig'
    )
    assert 'sqlite://' in negative_guard.lower()
    assert 'pytest.raises' in negative_guard
    assert not violations, 'Tests must use migrated PostgreSQL schema: ' + ', '.join(violations)


@pytest.mark.no_database
def test_migration_environment_guards_testing_database_target():
    source = (PROJECT_ROOT / 'migrations' / 'env.py').read_text(encoding='utf-8-sig')
    assert 'assert_testing_database' in source
    assert "endswith('_test')" in source
    assert 'TEST_DATABASE_URL' in source