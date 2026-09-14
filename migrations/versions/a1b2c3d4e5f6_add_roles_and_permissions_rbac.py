"""add_roles_and_permissions_rbac

Revision ID: a1b2c3d4e5f6
Revises: e1f2a3b4c5d6
Create Date: 2026-09-14 15:00:00.000000
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Catalogue de départ des permissions granulaires du back-office.
_PERMISSIONS = [
    ("packages.read", "Consulter le catalogue de packages"),
    ("packages.write", "Créer, modifier, activer/désactiver un package"),
    ("subscriptions.write", "Assigner, prolonger ou résilier un abonnement"),
    ("users.read", "Consulter la liste des artisans"),
    ("users.grant_pass", "Attribuer manuellement un Pass à un artisan"),
    ("documents.write", "Ingérer un document technique"),
    ("documents.delete", "Supprimer un document de la base de connaissances"),
    ("transactions.read", "Consulter le journal des transactions Mobile Money"),
    ("logs.read", "Consulter les journaux système"),
    ("roles.read", "Consulter les rôles et permissions"),
    ("roles.write", "Assigner un rôle RBAC à un administrateur"),
    ("audit.read", "Consulter le journal d'audit"),
]

# Rôles pré-configurés et les permissions qui leur sont accordées.
_ROLES: dict[str, tuple[str, list[str]]] = {
    "super_admin": ("Super Administrateur", [code for code, _ in _PERMISSIONS]),
    "support": (
        "Support Client",
        ["packages.read", "subscriptions.write", "users.read", "users.grant_pass"],
    ),
    "moderateur_contenu": (
        "Modérateur de Contenu",
        ["documents.write", "documents.delete", "logs.read"],
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("permissions"):
        op.create_table(
            "permissions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(100), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
        )
        op.create_index(
            "ix_permissions_code", "permissions", ["code"], unique=True
        )

    if not inspector.has_table("roles"):
        op.create_table(
            "roles",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(50), nullable=False),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_roles_code", "roles", ["code"], unique=True)

    if not inspector.has_table("role_permissions"):
        op.create_table(
            "role_permissions",
            sa.Column(
                "role_id",
                UUID(as_uuid=True),
                sa.ForeignKey("roles.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "permission_id",
                UUID(as_uuid=True),
                sa.ForeignKey("permissions.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )

    users_columns = {col["name"] for col in inspector.get_columns("users")}
    if "role_id" not in users_columns:
        op.add_column(
            "users",
            sa.Column(
                "role_id",
                UUID(as_uuid=True),
                sa.ForeignKey("roles.id"),
                nullable=True,
            ),
        )
        op.create_index("ix_users_role_id", "users", ["role_id"])

    # ── Seed idempotent des permissions et rôles de départ ──
    permissions_table = sa.table(
        "permissions",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    roles_table = sa.table(
        "roles",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("label", sa.String),
    )
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", UUID(as_uuid=True)),
        sa.column("permission_id", UUID(as_uuid=True)),
    )

    existing_perm_codes = {
        row[0]
        for row in bind.execute(sa.select(permissions_table.c.code)).fetchall()
    }
    permission_ids: dict[str, uuid.UUID] = {
        row[1]: row[0]
        for row in bind.execute(
            sa.select(permissions_table.c.id, permissions_table.c.code)
        ).fetchall()
    }
    for code, description in _PERMISSIONS:
        if code in existing_perm_codes:
            continue
        new_id = uuid.uuid4()
        bind.execute(
            permissions_table.insert().values(
                id=new_id, code=code, description=description
            )
        )
        permission_ids[code] = new_id

    existing_role_codes = {
        row[0] for row in bind.execute(sa.select(roles_table.c.code)).fetchall()
    }
    role_ids: dict[str, uuid.UUID] = {
        row[1]: row[0]
        for row in bind.execute(
            sa.select(roles_table.c.id, roles_table.c.code)
        ).fetchall()
    }
    for code, (label, _perm_codes) in _ROLES.items():
        if code in existing_role_codes:
            continue
        new_id = uuid.uuid4()
        bind.execute(roles_table.insert().values(id=new_id, code=code, label=label))
        role_ids[code] = new_id

    existing_links = {
        (row[0], row[1])
        for row in bind.execute(
            sa.select(
                role_permissions_table.c.role_id, role_permissions_table.c.permission_id
            )
        ).fetchall()
    }
    for code, (_label, perm_codes) in _ROLES.items():
        role_id = role_ids[code]
        for perm_code in perm_codes:
            perm_id = permission_ids[perm_code]
            if (role_id, perm_id) in existing_links:
                continue
            bind.execute(
                role_permissions_table.insert().values(
                    role_id=role_id, permission_id=perm_id
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    users_columns = {col["name"] for col in inspector.get_columns("users")}
    if "role_id" in users_columns:
        op.drop_index("ix_users_role_id", table_name="users")
        op.drop_column("users", "role_id")

    if inspector.has_table("role_permissions"):
        op.drop_table("role_permissions")
    if inspector.has_table("roles"):
        op.drop_table("roles")
    if inspector.has_table("permissions"):
        op.drop_table("permissions")
