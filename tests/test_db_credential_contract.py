"""DB credential contract: every resolved DSN must be passwordless (AGENTS.md §9).

The only place a PostgreSQL password may exist is the libpq pgpass file
(%APPDATA%\\postgresql\\pgpass.conf on Windows, $HOME/.pgpass elsewhere).

A failure here means a credential is in scope (env var, TEST_DATABASE_URL,
.env file, or a passwordful DATABASE_URL). Fix the environment per
AGENTS.md §9 — never weaken this test and never re-add a password to
make it pass.
"""

import os
import re

from sqlalchemy.engine import make_url

from app.config import Config, TestingConfig

_EMBEDDED_PASSWORD = re.compile(r"^\w+://[^:/@\s]+:[^@\s]+@")


def _redact(url: str) -> str:
    """AGENTS.md §9.2 redaction — never print a credential-bearing URL."""
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***\2", url)


class TestDatabaseCredentialContract:
    def test_no_db_password_env_in_scope(self):
        assert not os.getenv("APP_DB_PASS"), "APP_DB_PASS must be unset/empty (AGENTS.md §9.2)"
        assert not os.getenv("DB_PASS"), "DB_PASS must be unset/empty (AGENTS.md §9.2)"

    def test_config_db_pass_is_empty(self):
        assert not Config.DB_PASS, "Config.DB_PASS resolved a password — use pgpass (AGENTS.md §9.1)"

    def test_config_database_uri_is_passwordless(self):
        uri = Config.SQLALCHEMY_DATABASE_URI
        assert uri, "SQLALCHEMY_DATABASE_URI did not resolve"
        assert not _EMBEDDED_PASSWORD.search(uri), f"embedded credential in app DSN: {_redact(uri)}"
        assert make_url(uri).password is None, "app DSN must carry no password — use pgpass (AGENTS.md §9)"

    def test_testing_config_uri_is_passwordless(self):
        uri = TestingConfig.SQLALCHEMY_DATABASE_URI
        assert uri, "TestingConfig.SQLALCHEMY_DATABASE_URI did not resolve"
        assert not _EMBEDDED_PASSWORD.search(uri), f"embedded credential in test DSN: {_redact(uri)}"
        assert make_url(uri).password is None, "test DSN must carry no password — use pgpass (AGENTS.md §9.1)"

    def test_test_database_url_env_is_passwordless(self):
        raw = os.getenv("TEST_DATABASE_URL")
        if raw:
            assert make_url(raw).password is None, "TEST_DATABASE_URL env must be passwordless (AGENTS.md §9.1)"
