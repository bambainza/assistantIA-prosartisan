"""add_notifications_and_fcm_token

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-14 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "channel", sa.String(20), nullable=False, server_default="in_app"
            ),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("body", sa.String(1000), nullable=False),
            sa.Column("read_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_notifications_user_id", "notifications", ["user_id"]
        )
        op.create_index(
            "ix_notifications_created_at", "notifications", ["created_at"]
        )

    users_columns = {col["name"] for col in inspector.get_columns("users")}
    if "fcm_device_token" not in users_columns:
        op.add_column(
            "users", sa.Column("fcm_device_token", sa.String(255), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    users_columns = {col["name"] for col in inspector.get_columns("users")}
    if "fcm_device_token" in users_columns:
        op.drop_column("users", "fcm_device_token")

    if inspector.has_table("notifications"):
        op.drop_table("notifications")
