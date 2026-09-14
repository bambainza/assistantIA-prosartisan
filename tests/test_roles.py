"""Tests pour le RBAC (rôles & permissions) du back-office admin.

Régression sécurité : sans `require_permission`, un admin disposant d'un rôle
restreint pourrait effectuer des actions hors de son périmètre (ex: assigner
un rôle sans détenir la permission `roles.write`) — ces tests échoueraient
sans le garde-fou introduit dans `app.middleware.auth.require_permission`.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.role import Permission, Role
from app.models.user import User
from tests.conftest import mock_get_db


@pytest.fixture
def legacy_admin_user():
    """Admin historique (is_admin=True) sans rôle RBAC : accès complet hérité."""
    return User(
        id=uuid.uuid4(),
        email="legacy_admin@prosartisan.ci",
        nom="Admin Historique",
        telephone="+22507000010",
        is_admin=True,
        role_id=None,
    )


@pytest.fixture
def restricted_role():
    """Rôle RBAC 'support' : seule la lecture des rôles est accordée."""
    role = Role(id=uuid.uuid4(), code="support", label="Support Client")
    role.permissions = [Permission(id=uuid.uuid4(), code="roles.read")]
    return role


@pytest.fixture
def restricted_admin_user(restricted_role):
    """Admin avec un rôle RBAC restreint (permission 'roles.read' uniquement)."""
    user = User(
        id=uuid.uuid4(),
        email="support_admin@prosartisan.ci",
        nom="Admin Support",
        telephone="+22507000011",
        is_admin=True,
    )
    user.role = restricted_role
    return user


def _db_returning_acting_user(acting_user):
    """Mock DB : toute requête `SELECT ... FROM users` renvoie `acting_user`."""

    async def custom_mock_db():
        session = MagicMock()

        async def mock_execute(stmt):
            stmt_str = str(stmt)
            mock_res = MagicMock()
            is_roles_or_permissions_query = (
                "roles" in stmt_str and "role_permissions" not in stmt_str
            ) or "permissions" in stmt_str
            if is_roles_or_permissions_query:
                mock_res.scalars.return_value.all.return_value = []
            else:
                mock_res.scalar_one_or_none.return_value = acting_user
            return mock_res

        session.execute = mock_execute
        session.commit = AsyncMock()
        yield session

    return custom_mock_db


@pytest.mark.asyncio
async def test_legacy_admin_sans_role_a_acces_complet(legacy_admin_user):
    """Un admin historique sans rôle RBAC garde l'accès complet (compatibilité descendante)."""
    app.dependency_overrides[get_db] = _db_returning_acting_user(legacy_admin_user)
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/admin/roles", headers={"Authorization": f"Bearer {token}"}
            )
        assert res.status_code == 200
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_role_restreint_autorise_sa_propre_permission(restricted_admin_user):
    """Un admin avec le rôle 'support' (permission 'roles.read') peut lister les rôles."""
    app.dependency_overrides[get_db] = _db_returning_acting_user(restricted_admin_user)
    token = create_access_token(data={"sub": str(restricted_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/admin/roles", headers={"Authorization": f"Bearer {token}"}
            )
        assert res.status_code == 200
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_role_restreint_bloque_permission_non_accordee(restricted_admin_user):
    """Un admin avec le rôle 'support' ne peut PAS assigner de rôle (permission 'roles.write' absente)."""
    app.dependency_overrides[get_db] = _db_returning_acting_user(restricted_admin_user)
    token = create_access_token(data={"sub": str(restricted_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/users/{uuid.uuid4()}/role",
                headers={"Authorization": f"Bearer {token}"},
                json={"role_code": "support"},
            )
        assert res.status_code == 403
        assert "roles.write" in res.json()["detail"]
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_non_admin_rejete_sur_roles():
    """Un utilisateur non-admin n'a jamais accès aux routes RBAC."""
    non_admin_id = uuid.uuid4()

    async def non_admin_db():
        session = MagicMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_res)
        yield session

    app.dependency_overrides[get_db] = non_admin_db
    token = create_access_token(data={"sub": str(non_admin_id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/admin/roles", headers={"Authorization": f"Bearer {token}"}
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_assign_role_success(legacy_admin_user, restricted_role):
    """Un admin avec accès complet peut assigner un rôle RBAC à un autre compte."""
    target_user = User(
        id=uuid.uuid4(),
        email="target@prosartisan.ci",
        nom="Cible",
        telephone="+22507000013",
        is_admin=True,
        role_id=None,
    )
    call_sequence = [legacy_admin_user, target_user, restricted_role]

    async def custom_mock_db():
        session = MagicMock()

        async def mock_execute(stmt):
            mock_res = MagicMock()
            mock_res.scalar_one_or_none.return_value = call_sequence.pop(0)
            return mock_res

        session.execute = mock_execute
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/users/{target_user.id}/role",
                headers={"Authorization": f"Bearer {token}"},
                json={"role_code": "support"},
            )
        assert res.status_code == 200
        assert res.json()["status"] == "success"
        assert res.json()["role_code"] == "support"
    finally:
        app.dependency_overrides[get_db] = mock_get_db
