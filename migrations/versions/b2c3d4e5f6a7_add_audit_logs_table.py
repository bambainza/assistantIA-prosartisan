"""add_audit_logs_table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-14 15:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "actor_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("action", sa.String(100), nullable=False),
            sa.Column("resource_type", sa.String(50), nullable=False),
            sa.Column("resource_id", sa.String(100), nullable=True),
            sa.Column(
                "before_json",
                JSONB().with_variant(sa.Text(), "sqlite"),
                nullable=True,
            ),
            sa.Column(
                "after_json",
                JSONB().with_variant(sa.Text(), "sqlite"),
                nullable=True,
            ),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
        op.create_index(
            "ix_audit_logs_resource_type", "audit_logs", ["resource_type"]
        )
        op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("audit_logs"):
        op.drop_table("audit_logs")
