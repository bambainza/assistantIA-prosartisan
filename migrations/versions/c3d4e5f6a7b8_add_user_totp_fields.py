"""add_user_totp_fields

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-14 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    users_columns = {col["name"] for col in inspector.get_columns("users")}

    if "totp_secret" not in users_columns:
        op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))

    if "totp_enabled" not in users_columns:
        op.add_column(
            "users",
            sa.Column(
                "totp_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    users_columns = {col["name"] for col in inspector.get_columns("users")}

    if "totp_enabled" in users_columns:
        op.drop_column("users", "totp_enabled")
    if "totp_secret" in users_columns:
        op.drop_column("users", "totp_secret")
