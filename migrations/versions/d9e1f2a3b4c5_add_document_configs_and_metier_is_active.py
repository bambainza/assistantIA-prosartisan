"""add_document_configs_and_metier_is_active

Revision ID: d9e1f2a3b4c5
Revises: c8d1e2f3a4b5
Create Date: 2026-09-14 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "d9e1f2a3b4c5"
down_revision: str | None = "c8d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Ajouter is_active sur metiers si absent
    metiers_cols = {col["name"] for col in inspector.get_columns("metiers")}
    if "is_active" not in metiers_cols:
        op.add_column(
            "metiers",
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )

    # 2. Créer document_configs si absent
    if not inspector.has_table("document_configs"):
        op.create_table(
            "document_configs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("metier_id", sa.Integer(), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_document_configs_filename",
            "document_configs",
            ["filename"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("document_configs"):
        op.drop_table("document_configs")

    metiers_cols = {col["name"] for col in inspector.get_columns("metiers")}
    if "is_active" in metiers_cols:
        op.drop_column("metiers", "is_active")
