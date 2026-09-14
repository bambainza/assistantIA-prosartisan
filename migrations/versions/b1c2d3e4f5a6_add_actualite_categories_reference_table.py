"""add_actualite_categories_reference_table

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-09-14 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Catégories historiquement codées en dur (voir ancien
# `app.schemas.actualite.CATEGORIES_VALIDES`) — reprises ici comme données
# de référence initiales du module Paramètres, pour ne rien casser sur les
# actualités déjà publiées avec l'une de ces valeurs.
_CATEGORIES_INITIALES = [
    ("annonce", "Annonce"),
    ("maintenance", "Maintenance"),
    ("conseil", "Conseil"),
    ("promotion", "Promotion"),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "actualite_categories" not in inspector.get_table_names():
        op.create_table(
            "actualite_categories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(30), nullable=False, unique=True),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        table = sa.table(
            "actualite_categories",
            sa.column("code", sa.String),
            sa.column("label", sa.String),
        )
        op.bulk_insert(
            table,
            [{"code": code, "label": label} for code, label in _CATEGORIES_INITIALES],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "actualite_categories" in inspector.get_table_names():
        op.drop_table("actualite_categories")
