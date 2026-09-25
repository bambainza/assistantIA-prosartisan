"""quota_credits_requetes

Sépare le quota gratuit journalier (désormais un compteur Redis par jour) des
crédits de requêtes achetés (Pack 50, forfaits CREDITS), seuls conservés en
base. La colonne `requetes_restantes_gratuites` devient `credits_requetes`.

Reprise des données : une valeur <= 5 correspond au quota gratuit initial
(jamais rechargé jusqu'ici) et non à un achat — elle est remise à 0, le
quota journalier prenant le relais. Une valeur > 5 provient d'un pack acheté
et est conservée intégralement (au bénéfice de l'artisan).

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-09-25 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _colonnes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    colonnes = _colonnes("quotas_utilisateurs")
    if (
        "requetes_restantes_gratuites" in colonnes
        and "credits_requetes" not in colonnes
    ):
        op.alter_column(
            "quotas_utilisateurs",
            "requetes_restantes_gratuites",
            new_column_name="credits_requetes",
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default="0",
        )
        op.execute(
            "UPDATE quotas_utilisateurs SET credits_requetes = 0 "
            "WHERE credits_requetes <= 5"
        )


def downgrade() -> None:
    colonnes = _colonnes("quotas_utilisateurs")
    if (
        "credits_requetes" in colonnes
        and "requetes_restantes_gratuites" not in colonnes
    ):
        op.alter_column(
            "quotas_utilisateurs",
            "credits_requetes",
            new_column_name="requetes_restantes_gratuites",
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=None,
        )
