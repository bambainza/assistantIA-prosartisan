"""add_payment_methods_reference_table

Table de configuration des moyens de paiement (Wave, Orange Money, CinetPay)
permettant de les activer ou désactiver depuis le back-office.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-11-13 16:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OPERATEURS_INITIAUX = [
    ("WAVE", "Wave"),
    ("ORANGE", "Orange Money"),
    ("CINETPAY", "CinetPay"),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "payment_methods" not in inspector.get_table_names():
        op.create_table(
            "payment_methods",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(20), nullable=False, unique=True),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        table = sa.table(
            "payment_methods",
            sa.column("code", sa.String),
            sa.column("label", sa.String),
        )
        op.bulk_insert(
            table,
            [{"code": code, "label": label} for code, label in _OPERATEURS_INITIAUX],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "payment_methods" in inspector.get_table_names():
        op.drop_table("payment_methods")

