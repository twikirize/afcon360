"""Wallet-owned marketplace invoice and transport reference.

Revision ID: wltinv261029
Revises: fc87cdbd0e6a
Create Date: 2026-10-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "wltinv261029"
down_revision = "fc87cdbd0e6a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wallet_marketplace_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("service_code", sa.String(length=50), nullable=False),
        sa.Column("service_reference", sa.String(length=255), nullable=False),
        sa.Column("payer_user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("payment_method", sa.String(length=50), nullable=False),
        sa.Column(
            "settlement_timing", sa.String(length=32), nullable=False,
            server_default="pay_on_completion",
        ),
        sa.Column("service_country_code", sa.String(length=2), nullable=True),
        sa.Column("payer_country_code", sa.String(length=2), nullable=True),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default="pending",
        ),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("cash_received_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "invoice_metadata", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "receipt_metadata", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cash_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "amount > 0", name="ck_marketplace_invoice_amount_positive",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'due', 'paid', 'cash_received', 'failed', 'cancelled', 'refunded')",
            name="ck_marketplace_invoice_status_valid",
        ),
        sa.CheckConstraint(
            "settlement_timing IN ('pay_on_completion')",
            name="ck_marketplace_invoice_timing_valid",
        ),
        sa.ForeignKeyConstraint(
            ["payer_user_id"], ["users.id"],
            name="fk_wallet_marketplace_invoice_payer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"], ["transactions.id"],
            name="fk_wallet_marketplace_invoice_transaction",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cash_received_by_user_id"], ["users.id"],
            name="fk_wallet_marketplace_invoice_cash_receiver",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_wallet_marketplace_invoices"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_wallet_marketplace_invoice_idempotency",
        ),
        sa.UniqueConstraint(
            "service_code", "service_reference",
            name="uq_marketplace_invoice_service_reference",
        ),
    )
    op.create_index(
        "ix_wallet_marketplace_invoice_payer_status",
        "wallet_marketplace_invoices", ["payer_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_wallet_marketplace_invoice_status_created",
        "wallet_marketplace_invoices", ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_wallet_marketplace_invoice_transaction",
        "wallet_marketplace_invoices", ["transaction_id"],
        unique=False,
    )

    # Thin transport-side reference only. Wallet invoice/transaction data and
    # all financial decisions remain owned by Wallet.
    op.add_column(
        "transport_booking_payments",
        sa.Column("wallet_invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_transport_payment_wallet_invoice",
        "transport_booking_payments",
        "wallet_marketplace_invoices",
        ["wallet_invoice_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_transport_booking_payments_wallet_invoice_id",
        "transport_booking_payments", ["wallet_invoice_id"], unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_transport_booking_payments_wallet_invoice_id",
        table_name="transport_booking_payments",
    )
    op.drop_constraint(
        "fk_transport_payment_wallet_invoice",
        "transport_booking_payments",
        type_="foreignkey",
    )
    op.drop_column("transport_booking_payments", "wallet_invoice_id")

    op.drop_index(
        "ix_wallet_marketplace_invoice_transaction",
        table_name="wallet_marketplace_invoices",
    )
    op.drop_index(
        "ix_wallet_marketplace_invoice_status_created",
        table_name="wallet_marketplace_invoices",
    )
    op.drop_index(
        "ix_wallet_marketplace_invoice_payer_status",
        table_name="wallet_marketplace_invoices",
    )
    op.drop_table("wallet_marketplace_invoices")
