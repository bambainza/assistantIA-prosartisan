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


def _users_columns() -> set[str]:
    bind = op.get_bind()
    return {col["name"] for col in sa.inspect(bind).get_columns("users")}


def upgrade() -> None:
    # Idempotent : la colonne peut déjà exister si Base.metadata.create_all
    # (init_db) a tourné avant l'application des migrations.
    if "is_admin" not in _users_columns():
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
    if "is_admin" in _users_columns():
        op.drop_column("users", "is_admin")
