"""add_push_subscriptions_table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-14 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("push_subscriptions"):
        op.create_table(
            "push_subscriptions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("endpoint", sa.Text(), nullable=False),
            sa.Column("p256dh_key", sa.String(255), nullable=False),
            sa.Column("auth_key", sa.String(100), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"]
        )
        op.create_index(
            "ix_push_subscriptions_endpoint",
            "push_subscriptions",
            ["endpoint"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("push_subscriptions"):
        op.drop_table("push_subscriptions")
