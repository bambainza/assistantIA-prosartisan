"""add_actualites_table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-14 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("actualites"):
        op.create_table(
            "actualites",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("titre", sa.String(200), nullable=False),
            sa.Column("contenu", sa.Text(), nullable=False),
            sa.Column(
                "metier_id",
                sa.Integer(),
                sa.ForeignKey("metiers.id"),
                nullable=True,
            ),
            sa.Column(
                "statut", sa.String(20), nullable=False, server_default="brouillon"
            ),
            sa.Column(
                "created_by",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("publie_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_actualites_statut", "actualites", ["statut"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("actualites"):
        op.drop_table("actualites")
