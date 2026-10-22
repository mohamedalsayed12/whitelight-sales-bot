"""create leads

Revision ID: 007_leads
Revises: 006_cheque_collected_at
Create Date: 2026-10-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_leads"
down_revision: str | None = "006_cheque_collected_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("area", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reasons", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("pitch_hook", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("contact_by", sa.Date(), nullable=True),
        sa.Column("quote_sent_on", sa.Date(), nullable=True),
        sa.Column("assigned_salesman_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("suggested_salesman_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('new', 'contacted', 'quote_sent', 'won')",
            name="ck_leads_status",
        ),
        sa.CheckConstraint(
            "source IN ('tender', 'exhibition', 'hand', 'referral')",
            name="ck_leads_source",
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_leads_score"),
    )


def downgrade() -> None:
    op.drop_table("leads")
