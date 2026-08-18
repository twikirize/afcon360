"""Executable checks for the PostgreSQL and SQLAlchemy-only test contract."""

import ast
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.config import TestingConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _python_files(directory: Path, pattern: str):
    return sorted(directory.rglob(pattern))


def _forbidden_sqlalchemy_text_nodes(path: Path):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {'sqlalchemy', 'sqlalchemy.sql'}:
            if any(alias.name == 'text' for alias in node.names):
                yield node
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == 'text':
                yield node
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'execute'
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.strip().upper().startswith(
                ('SELECT ', 'INSERT ', 'UPDATE ', 'DELETE ', 'ALTER ', 'CREATE ', 'DROP ')
            )
        ):
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
        for node in _forbidden_sqlalchemy_text_nodes(path)
    ]
    assert not violations, 'Use SQLAlchemy models/expressions instead of text(): ' + ', '.join(violations)


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
        if 'sqlite://' in source.lower():
            violations.append(f'{path}:sqlite')
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {'create_all', 'drop_all'}:
                    violations.append(f'{path}:{node.lineno}:{node.func.attr}')

    assert not violations, 'Tests must use migrated PostgreSQL schema: ' + ', '.join(violations)


@pytest.mark.no_database
def test_migration_environment_guards_testing_database_target():
    source = (PROJECT_ROOT / 'migrations' / 'env.py').read_text(encoding='utf-8-sig')
    assert 'assert_testing_database' in source
    assert "endswith('_test')" in source
    assert 'TEST_DATABASE_URL' in source