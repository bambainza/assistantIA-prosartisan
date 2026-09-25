"""transaction_provider_fields

Champs opérateur des transactions Mobile Money (parcours officiels Wave
Checkout et Orange Money WebPay) : identifiant de session / pay_token,
notif_token Orange Money, identifiant de transaction opérateur et URL de
paiement.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-25 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "transactions_mobile_money"
_COLONNES = (
    ("provider_session_id", sa.String(255)),
    ("provider_notif_token", sa.String(255)),
    ("provider_transaction_id", sa.String(255)),
    ("payment_url", sa.String(1024)),
)
_INDEX = ("provider_session_id", "provider_notif_token")


def _colonnes_existantes() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existantes = _colonnes_existantes()
    for nom, type_ in _COLONNES:
        if nom not in existantes:
            op.add_column(_TABLE, sa.Column(nom, type_, nullable=True))
    for nom in _INDEX:
        if nom not in existantes:
            op.create_index(f"ix_{_TABLE}_{nom}", _TABLE, [nom])


def downgrade() -> None:
    existantes = _colonnes_existantes()
    for nom in _INDEX:
        if nom in existantes:
            op.drop_index(f"ix_{_TABLE}_{nom}", table_name=_TABLE)
    for nom, _ in reversed(_COLONNES):
        if nom in existantes:
            op.drop_column(_TABLE, nom)
