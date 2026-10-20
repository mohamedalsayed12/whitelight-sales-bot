"""create products, clients, and invoices

Revision ID: 002_products_clients_invoices
Revises: 001_create_users
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_products_clients_invoices"
down_revision: str | None = "001_create_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), server_default=sa.text("''"), nullable=False),
        sa.Column("unit", sa.String(length=32), server_default="pcs", nullable=False),
        sa.Column("stock_on_hand", sa.Numeric(12, 3), server_default="0", nullable=False),
        sa.Column("reorder_level", sa.Numeric(12, 3), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("stock_on_hand >= 0", name="ck_products_stock_non_negative"),
        sa.CheckConstraint("reorder_level >= 0", name="ck_products_reorder_non_negative"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
    )
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=20), server_default="other", nullable=False),
        sa.Column("price_list", sa.String(length=20), nullable=True),
        sa.Column("credit_limit", sa.Numeric(12, 3), server_default="0", nullable=False),
        sa.Column("assigned_salesman_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("phone", sa.String(length=50), server_default=sa.text("''"), nullable=False),
        sa.Column("cr_number", sa.String(length=50), nullable=True),
        sa.CheckConstraint(
            "type IN ('hotel', 'restaurant', 'other')",
            name="ck_clients_type",
        ),
        sa.CheckConstraint(
            "price_list IS NULL OR price_list IN ('hotel', 'restaurant')",
            name="ck_clients_price_list",
        ),
        sa.CheckConstraint("credit_limit >= 0", name="ck_clients_credit_limit_non_negative"),
        sa.UniqueConstraint("name", name="uq_clients_name"),
    )
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("amount_paid", sa.Numeric(12, 3), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_invoices_amount_non_negative"),
        sa.CheckConstraint("amount_paid >= 0", name="ck_invoices_amount_paid_non_negative"),
        sa.CheckConstraint("amount_paid <= amount", name="ck_invoices_paid_not_above_amount"),
        sa.UniqueConstraint("number", name="uq_invoices_number"),
    )


def downgrade() -> None:
    op.drop_table("invoices")
    op.drop_table("clients")
    op.drop_table("products")
