"""add_user_oauth_and_email_fields

Revision ID: f9a3a3385da9
Revises: 1a2b3c4d5e6f
Create Date: 2026-08-21 11:08:19.906437
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9a3a3385da9"
down_revision: str | None = "1a2b3c4d5e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Ajouter la colonne email
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # 2. Modifier la colonne telephone pour la rendre nullable
    op.alter_column(
        "users", "telephone", existing_type=sa.String(length=20), nullable=True
    )

    # 3. Ajouter les colonnes OAuth
    op.add_column("users", sa.Column("google_id", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_users_google_id"), "users", ["google_id"], unique=True)

    op.add_column(
        "users", sa.Column("avatar_url", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(length=20),
            nullable=False,
            server_default="local",
        ),
    )


def downgrade() -> None:
    # 1. Supprimer la colonne auth_provider et avatar_url
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "avatar_url")

    # 2. Supprimer google_id et son index
    op.drop_index(op.f("ix_users_google_id"), table_name="users")
    op.drop_column("users", "google_id")

    # 3. Rendre la colonne telephone non nullable
    op.alter_column(
        "users", "telephone", existing_type=sa.String(length=20), nullable=False
    )

    # 4. Supprimer email et son index
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_column("users", "email")
