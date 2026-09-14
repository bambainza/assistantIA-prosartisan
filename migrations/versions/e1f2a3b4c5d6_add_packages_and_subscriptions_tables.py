"""add_packages_and_subscriptions_tables

Revision ID: e1f2a3b4c5d6
Revises: d9e1f2a3b4c5
Create Date: 2026-09-14 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d9e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Créer la table packages si absente
    if not inspector.has_table("packages"):
        op.create_table(
            "packages",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(50), nullable=False),
            sa.Column("nom", sa.String(100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("prix", sa.Integer(), nullable=False),
            sa.Column("devise", sa.String(5), nullable=False, server_default="XOF"),
            sa.Column(
                "type_package",
                sa.String(20),
                nullable=False,
                server_default="DURATION",
            ),
            sa.Column("duree_jours", sa.Integer(), nullable=True),
            sa.Column("quota_requetes", sa.Integer(), nullable=True),
            sa.Column(
                "auto_renouvelable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "est_actif",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "fonctionnalites",
                JSONB().with_variant(sa.Text(), "sqlite"),
                nullable=True,
            ),
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
        op.create_index("ix_packages_code", "packages", ["code"], unique=True)
        op.create_index("ix_packages_est_actif", "packages", ["est_actif"])

    # 2. Créer la table user_subscriptions si absente
    if not inspector.has_table("user_subscriptions"):
        op.create_table(
            "user_subscriptions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "package_id",
                UUID(as_uuid=True),
                sa.ForeignKey("packages.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "statut",
                sa.String(20),
                nullable=False,
                server_default="ACTIVE",
            ),
            sa.Column(
                "date_debut",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("date_fin", sa.DateTime(), nullable=True),
            sa.Column("quota_initial", sa.Integer(), nullable=True),
            sa.Column(
                "quota_consomme",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "renouvellement_auto",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "date_prochain_renouvellement", sa.DateTime(), nullable=True
            ),
            sa.Column(
                "tentatives_renouvellement",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
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
        op.create_index(
            "ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"]
        )
        op.create_index(
            "ix_user_subscriptions_package_id",
            "user_subscriptions",
            ["package_id"],
        )
        op.create_index(
            "ix_user_subscriptions_statut", "user_subscriptions", ["statut"]
        )
        op.create_index(
            "ix_user_subscriptions_date_fin",
            "user_subscriptions",
            ["date_fin"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("user_subscriptions"):
        op.drop_table("user_subscriptions")

    if inspector.has_table("packages"):
        op.drop_table("packages")
