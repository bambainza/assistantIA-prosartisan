"""add_quotes_table

Revision ID: e7f8a9b0c1d2
Revises: b1c2d3e4f5a6
Create Date: 2026-09-19 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("quotes"):
        op.create_table(
            "quotes",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("numero", sa.String(50), unique=True, nullable=False, index=True),
            sa.Column("titre", sa.String(200), nullable=False),
            sa.Column("client_nom", sa.String(150), nullable=False),
            sa.Column("client_telephone", sa.String(50), nullable=True),
            sa.Column("client_adresse", sa.String(255), nullable=True),
            sa.Column(
                "metier_id",
                sa.Integer(),
                sa.ForeignKey("metiers.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("statut", sa.String(30), nullable=False, server_default="BROUILLON", index=True),
            sa.Column("items", sa.JSON(), nullable=False),
            sa.Column("total_ht", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("remise_pct", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("tva_pct", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("total_ttc", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("acompte_demande_pct", sa.Float(), nullable=False, server_default="30.0"),
            sa.Column("montant_acompte", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("mode_paiement", sa.String(50), nullable=False, server_default="Wave / Orange Money"),
            sa.Column("delai_jours", sa.Integer(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("date_emission", sa.DateTime(), nullable=False),
            sa.Column("date_validite", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("quotes"):
        op.drop_table("quotes")
