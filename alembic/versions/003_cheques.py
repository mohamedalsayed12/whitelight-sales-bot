"""create cheques

Revision ID: 003_cheques
Revises: 002_products_clients_invoices
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_cheques"
down_revision: str | None = "002_products_clients_invoices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cheques",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("cheque_number", sa.String(length=64), nullable=False),
        sa.Column("bank", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("collected_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint(
            "status IN ('received', 'deposited', 'cleared', 'bounced')",
            name="ck_cheques_status",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_cheques_amount_non_negative"),
    )


def downgrade() -> None:
    op.drop_table("cheques")
