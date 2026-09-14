"""add_finance_and_communication_fields

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-14 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── Module Finance : remboursement d'une transaction Mobile Money ──
    txn_columns = {c["name"] for c in inspector.get_columns("transactions_mobile_money")}
    if "refunded_at" not in txn_columns:
        op.add_column(
            "transactions_mobile_money",
            sa.Column("refunded_at", sa.DateTime(), nullable=True),
        )
    if "refund_reason" not in txn_columns:
        op.add_column(
            "transactions_mobile_money",
            sa.Column("refund_reason", sa.String(255), nullable=True),
        )
    if "refunded_by_admin_id" not in txn_columns:
        op.add_column(
            "transactions_mobile_money",
            sa.Column(
                "refunded_by_admin_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    # ── Module Communication : workflow éditorial des actualités ──
    actu_columns = {c["name"] for c in inspector.get_columns("actualites")}
    if "category" not in actu_columns:
        op.add_column(
            "actualites",
            sa.Column(
                "category", sa.String(30), nullable=False, server_default="annonce"
            ),
        )
    if "target_audience" not in actu_columns:
        op.add_column(
            "actualites",
            sa.Column(
                "target_audience", sa.String(30), nullable=False, server_default="tous"
            ),
        )
    if "scheduled_at" not in actu_columns:
        op.add_column(
            "actualites",
            sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    actu_columns = {c["name"] for c in inspector.get_columns("actualites")}
    if "scheduled_at" in actu_columns:
        op.drop_column("actualites", "scheduled_at")
    if "target_audience" in actu_columns:
        op.drop_column("actualites", "target_audience")
    if "category" in actu_columns:
        op.drop_column("actualites", "category")

    txn_columns = {c["name"] for c in inspector.get_columns("transactions_mobile_money")}
    if "refunded_by_admin_id" in txn_columns:
        op.drop_column("transactions_mobile_money", "refunded_by_admin_id")
    if "refund_reason" in txn_columns:
        op.drop_column("transactions_mobile_money", "refund_reason")
    if "refunded_at" in txn_columns:
        op.drop_column("transactions_mobile_money", "refunded_at")
