"""create price lists and orders

Revision ID: 004_orders
Revises: 003_cheques
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_orders"
down_revision: str | None = "003_cheques"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.UniqueConstraint("name", name="uq_price_lists_name"),
    )
    op.execute("INSERT INTO price_lists (name) VALUES ('hotel'), ('restaurant')")
    op.create_table(
        "price_list_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("price_list_id", sa.Integer(), sa.ForeignKey("price_lists.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 3), nullable=False),
        sa.CheckConstraint("unit_price > 0", name="ck_price_list_items_price_positive"),
        sa.UniqueConstraint("price_list_id", "product_id", name="uq_price_list_items_product"),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("salesman_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('submitted', 'approved', 'out_for_delivery', 'delivered', 'cancelled')",
            name="ck_orders_status",
        ),
    )
    op.create_table(
        "order_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 3), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_lines_quantity_positive"),
        sa.CheckConstraint("unit_price > 0", name="ck_order_lines_price_positive"),
        sa.UniqueConstraint("order_id", "product_id", name="uq_order_lines_product"),
    )
    op.create_table(
        "order_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("changed_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("order_history")
    op.drop_table("order_lines")
    op.drop_table("orders")
    op.drop_table("price_list_items")
    op.drop_table("price_lists")
