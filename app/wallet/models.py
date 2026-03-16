from datetime import datetime
from sqlalchemy import UniqueConstraint, Index
from app.extensions import db


class Wallet(db.Model):
    """
    A wallet that can belong to either a User or an Organisation.
    Each owner can have exactly one wallet.
    """
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_wallet_user"),
        UniqueConstraint("organisation_id", name="uq_wallet_org"),
        Index("ix_wallets_currency_pair", "home_currency", "local_currency"),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    # Explicit ownership
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    organisation_id = db.Column(db.BigInteger, db.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True, index=True)

    # Wallet metadata
    home_currency = db.Column(db.String(10), nullable=False, default="USD")
    local_currency = db.Column(db.String(10), nullable=False, default="UGX")
    nationality = db.Column(db.String(5), default="UG")
    location = db.Column(db.String(5), default="UG")
    verified = db.Column(db.Boolean, nullable=False, default=False)

    # Balances
    balance_home = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    balance_local = db.Column(db.Numeric(18, 2), nullable=False, default=0)

    # Optimistic lock + lifecycle
    version = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = db.relationship("User", back_populates="wallet", uselist=False)
    organisation = db.relationship("Organisation", back_populates="wallet", uselist=False)

    def __repr__(self):
        return f"<Wallet id={self.id} user_id={self.user_id} org_id={self.organisation_id}>"


class Transaction(db.Model):
    """
    Immutable transaction ledger for a wallet.
    """
    __tablename__ = "wallet_transactions"
    __table_args__ = (
        Index("ix_wallet_tx_wallet_id", "wallet_id"),
        Index("ix_wallet_tx_type_currency", "type", "currency"),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    wallet_id = db.Column(db.BigInteger, db.ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)

    # Identifiers
    tx_id = db.Column(db.String(64), index=True, nullable=True)
    client_request_id = db.Column(db.String(128), index=True, nullable=True)

    # Transaction details
    type = db.Column(db.String(40), nullable=False)  # deposit, withdraw, transfer
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(10), nullable=False)
    meta = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationship back to wallet
    wallet = db.relationship(
        "Wallet",
        backref=db.backref("transactions", lazy="dynamic", cascade="all, delete-orphan"),
        lazy="joined",
    )

    def __repr__(self):
        return f"<Transaction id={self.id} wallet_id={self.wallet_id} type={self.type} amount={self.amount} {self.currency}>"
