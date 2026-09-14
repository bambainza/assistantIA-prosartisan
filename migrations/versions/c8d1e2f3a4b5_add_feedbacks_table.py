"""add_feedbacks_table

Revision ID: c8d1e2f3a4b5
Revises: b7c9d1e2f3a4
Create Date: 2026-09-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "c8d1e2f3a4b5"
down_revision: str | None = "b7c9d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("feedbacks"):
        op.create_table(
            "feedbacks",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "conversation_id",
                UUID(as_uuid=True),
                sa.ForeignKey("conversations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("message_id", sa.String(100), nullable=True),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_feedbacks_user_id", "feedbacks", ["user_id"])
        op.create_index("ix_feedbacks_conversation_id", "feedbacks", ["conversation_id"])
        op.create_index("ix_feedbacks_message_id", "feedbacks", ["message_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("feedbacks"):
        op.drop_table("feedbacks")
