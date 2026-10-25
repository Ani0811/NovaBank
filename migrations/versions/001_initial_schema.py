"""Initial schema creation for NovaBank: accounts, transactions, audit_events.

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-10-25 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Accounts Table
    op.create_table(
        "accounts",
        sa.Column("account_number", sa.String(length=12), nullable=False),
        sa.Column("holder_name", sa.String(length=100), nullable=False),
        sa.Column("dob", sa.Date(), nullable=False),
        sa.Column("address_line", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=False),
        sa.Column("phone_number", sa.String(length=15), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column(
            "balance", sa.Numeric(precision=15, scale=2), server_default="0.00", nullable=False
        ),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("balance >= 0.00", name="chk_accounts_balance_non_negative"),
        sa.PrimaryKeyConstraint("account_number"),
    )
    op.create_index("idx_accounts_holder_name", "accounts", ["holder_name"])
    op.create_index("idx_accounts_phone", "accounts", ["phone_number"])

    # 2. Transactions Table
    op.create_table(
        "transactions",
        sa.Column(
            "transaction_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("transaction_ref", sa.String(length=36), nullable=False),
        sa.Column("account_number", sa.String(length=12), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("balance_after", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("description", sa.String(length=255), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=50), server_default="system", nullable=False),
        sa.CheckConstraint("amount > 0.00", name="chk_transactions_amount_positive"),
        sa.ForeignKeyConstraint(
            ["account_number"], ["accounts.account_number"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("transaction_id"),
        sa.UniqueConstraint("transaction_ref"),
    )
    op.create_index("idx_transactions_account", "transactions", ["account_number"])
    op.create_index("idx_transactions_created_at", "transactions", ["created_at"])
    op.create_index("idx_transactions_ref", "transactions", ["transaction_ref"])

    # 3. Audit Events Table
    op.create_table(
        "audit_events",
        sa.Column(
            "event_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=50), nullable=False),
        sa.Column("actor", sa.String(length=50), server_default="system", nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("idx_audit_event_type", "audit_events", ["event_type"])
    op.create_index("idx_audit_entity", "audit_events", ["entity_type", "entity_id"])
    op.create_index("idx_audit_timestamp", "audit_events", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("transactions")
    op.drop_table("accounts")
