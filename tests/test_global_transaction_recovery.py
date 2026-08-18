"""Regression checks for application-wide SQLAlchemy transaction cleanup."""

from pathlib import Path


def test_request_lifecycle_recovers_inactive_sessions_and_always_rolls_back():
    source = Path("app/__init__.py").read_text(encoding="utf-8")
    before_start = source.index("def ensure_clean_transaction():")
    teardown_start = source.index("def handle_transaction(exception=None):")
    before_body = source[before_start:teardown_start]
    teardown_body = source[teardown_start:source.index("    # ------------------------------------------------------------------", teardown_start)]

    assert "if not db.session.is_active" in before_body
    assert before_body.index("db.session.rollback()") < before_body.index("db.session.expire_all()")
    assert "db.session.rollback()" in teardown_body
    assert "if exception:" not in teardown_body
    assert teardown_body.index("db.session.rollback()") < teardown_body.index("db.session.remove()")