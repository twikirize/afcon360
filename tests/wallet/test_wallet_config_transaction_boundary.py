"""Wallet configuration must not commit inside financial transactions."""

from app.extensions import db
from app.wallet.models.config import WalletSystemConfig


def _clear_wallet_config():
    db.session.query(WalletSystemConfig).delete()
    db.session.commit()
    db.session.remove()


def test_get_config_flushes_but_does_not_commit_inside_explicit_transaction(app):
    with app.app_context():
        _clear_wallet_config()

        with db.session.begin():
            config = WalletSystemConfig.get_config()
            assert config.id is not None
            transaction = db.session.get_transaction()
            assert transaction is not None
            assert getattr(transaction.origin, "name", None) == "BEGIN"

            # The getter must leave the transaction usable for subsequent
            # ledger/audit writes owned by the wallet operation.
            config.agents_enabled = True
            assert db.session.query(WalletSystemConfig).count() == 1

        db.session.remove()
        persisted = db.session.query(WalletSystemConfig).one()
        assert persisted.agents_enabled is True


def test_get_config_preserves_nested_transaction_savepoint(app):
    with app.app_context():
        _clear_wallet_config()

        with db.session.begin():
            with db.session.begin_nested():
                config = WalletSystemConfig.get_config()
                config.agents_enabled = True
                assert db.session.in_nested_transaction()
                assert db.session.query(WalletSystemConfig).count() == 1

            # The outer unit of work remains active after the nested savepoint.
            assert db.session.get_transaction() is not None

        db.session.remove()
        assert db.session.query(WalletSystemConfig).one().agents_enabled is True


def test_get_config_still_commits_lazy_initialization_without_explicit_begin(app):
    with app.app_context():
        _clear_wallet_config()

        # A normal query starts an autobegin transaction. The getter owns
        # lazy initialization in this case and must persist the row.
        assert WalletSystemConfig.get_config().id is not None
        db.session.remove()
        assert db.session.query(WalletSystemConfig).count() == 1
