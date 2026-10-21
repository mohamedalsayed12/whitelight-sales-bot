"""create quotes

Revision ID: 005_quotes
Revises: 004_orders
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_quotes"
down_revision: str | None = "004_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quotes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("salesman_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "quote_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quote_id", sa.Integer(), sa.ForeignKey("quotes.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 3), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_quote_lines_quantity_positive"),
        sa.CheckConstraint("unit_price > 0", name="ck_quote_lines_price_positive"),
        sa.UniqueConstraint("quote_id", "product_id", name="uq_quote_lines_product"),
    )


def downgrade() -> None:
    op.drop_table("quote_lines")
    op.drop_table("quotes")
