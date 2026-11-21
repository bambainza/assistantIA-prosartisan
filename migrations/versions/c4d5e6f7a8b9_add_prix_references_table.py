"""add_prix_references_table

Grille de prix de référence administrable : seule source des prix unitaires
pré-remplis dans les devis extraits par l'IA.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-11-21 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("prix_references"):
        op.create_table(
            "prix_references",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("designation", sa.String(200), nullable=False),
            sa.Column("unite", sa.String(30), nullable=False),
            sa.Column("prix_unitaire", sa.Integer(), nullable=False),
            sa.Column("type_item", sa.String(20), nullable=False),
            sa.Column("mots_cles", sa.String(500), nullable=True),
            sa.Column(
                "metier_id",
                sa.Integer(),
                sa.ForeignKey("metiers.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column("commune", sa.String(100), nullable=True),
            sa.Column("source", sa.String(255), nullable=True),
            sa.Column("date_releve", sa.Date(), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
                index=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("prix_references"):
        op.drop_table("prix_references")
