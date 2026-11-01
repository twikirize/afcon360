"""Wallet configuration must not commit inside financial transactions."""

from app.extensions import db
from app.wallet.models.config import WalletSystemConfig


def test_get_config_flushes_inside_explicit_transaction_without_early_commit(app):
    with app.app_context():
        db.session.remove()
        with db.session.begin():
            savepoint = db.session.begin_nested()
            try:
                db.session.query(WalletSystemConfig).delete(synchronize_session=False)
                db.session.flush()

                config = WalletSystemConfig.get_config()
                assert config.id is not None
                transaction = db.session().get_transaction()
                assert transaction is not None
                assert getattr(transaction.origin, "name", None) == "BEGIN"
                assert db.session().in_nested_transaction()

                # If the getter commits, subsequent operations inside the
                # caller's transaction raise InvalidRequestError.
                config.agents_enabled = True
                assert db.session.query(WalletSystemConfig).count() == 1
            finally:
                # Restore any pre-existing singleton row (or remove the
                # temporary one) without altering the outer test baseline.
                savepoint.rollback()
        db.session.remove()


def test_get_config_flushes_inside_autobegin_nested_savepoint(app):
    with app.app_context():
        db.session.remove()
        # begin_nested creates an AUTOBEGIN root and a managed savepoint.
        savepoint = db.session.begin_nested()
        try:
            db.session.query(WalletSystemConfig).delete(synchronize_session=False)
            db.session.flush()

            config = WalletSystemConfig.get_config()
            assert config.id is not None
            assert db.session().in_nested_transaction()
            config.agents_enabled = True
            assert db.session.query(WalletSystemConfig).count() == 1
        finally:
            savepoint.rollback()
            db.session.rollback()
        db.session.remove()
