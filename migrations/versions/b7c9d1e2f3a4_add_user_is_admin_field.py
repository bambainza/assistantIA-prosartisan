"""add_user_is_admin_field

Revision ID: b7c9d1e2f3a4
Revises: f9a3a3385da9
Create Date: 2026-09-04 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c9d1e2f3a4"
down_revision: str | None = "f9a3a3385da9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ajouter la colonne is_admin (NOT NULL, défaut False pour les lignes existantes)
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
