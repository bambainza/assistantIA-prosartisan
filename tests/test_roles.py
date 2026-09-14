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


def _sequenced_db(responses):
    """Mock DB : chaque appel `db.execute` consomme la réponse suivante de la liste.

    `responses` est une liste de tuples `("scalar", valeur)` pour un
    `scalar_one_or_none()` ou `("scalars", [valeurs])` pour un `scalars().all()`.
    """

    async def custom_mock_db():
        session = MagicMock()
        queue = list(responses)

        async def mock_execute(stmt):
            kind, value = queue.pop(0)
            mock_res = MagicMock()
            if kind == "scalar":
                mock_res.scalar_one_or_none.return_value = value
            else:
                mock_res.scalars.return_value.all.return_value = value
            return mock_res

        session.execute = mock_execute
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        yield session

    return custom_mock_db


@pytest.mark.asyncio
async def test_create_role_success(legacy_admin_user):
    """Un admin avec accès complet peut créer un rôle avec des permissions initiales."""
    new_permission = Permission(id=uuid.uuid4(), code="roles.read")
    app.dependency_overrides[get_db] = _sequenced_db(
        [
            ("scalar", legacy_admin_user),  # require_permission
            ("scalar", None),  # pas de conflit de code
            ("scalars", [new_permission]),  # résolution des permission_codes
        ]
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/admin/roles",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "code": "support_n2",
                    "label": "Support Niveau 2",
                    "permission_codes": ["roles.read"],
                },
            )
        assert res.status_code == 201
        body = res.json()
        assert body["code"] == "support_n2"
        assert [p["code"] for p in body["permissions"]] == ["roles.read"]
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_create_role_conflit_code_existant(legacy_admin_user, restricted_role):
    """La création échoue avec 409 si le code de rôle existe déjà."""
    app.dependency_overrides[get_db] = _sequenced_db(
        [
            ("scalar", legacy_admin_user),  # require_permission
            ("scalar", restricted_role),  # code déjà pris
        ]
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/admin/roles",
                headers={"Authorization": f"Bearer {token}"},
                json={"code": "support", "label": "Doublon"},
            )
        assert res.status_code == 409
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_create_role_bloque_sans_permission(restricted_admin_user):
    """Un admin sans la permission 'roles.write' ne peut pas créer de rôle."""
    app.dependency_overrides[get_db] = _sequenced_db(
        [("scalar", restricted_admin_user)]  # require_permission échoue ici
    )
    token = create_access_token(data={"sub": str(restricted_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/admin/roles",
                headers={"Authorization": f"Bearer {token}"},
                json={"code": "nouveau", "label": "Nouveau Rôle"},
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_update_role_permissions_success(legacy_admin_user, restricted_role):
    """Un admin avec accès complet peut activer/désactiver les permissions d'un rôle."""
    new_permission = Permission(id=uuid.uuid4(), code="audit.read")
    app.dependency_overrides[get_db] = _sequenced_db(
        [
            ("scalar", legacy_admin_user),  # require_permission
            ("scalar", restricted_role),  # rôle ciblé (permissions: roles.read)
            ("scalars", [new_permission]),  # nouveau jeu : audit.read seul
        ]
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.put(
                f"/api/admin/roles/{restricted_role.id}/permissions",
                headers={"Authorization": f"Bearer {token}"},
                json={"permission_codes": ["audit.read"]},
            )
        assert res.status_code == 200
        body = res.json()
        assert [p["code"] for p in body["permissions"]] == ["audit.read"]
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_update_role_permissions_role_introuvable(legacy_admin_user):
    """La mise à jour échoue avec 404 si le rôle n'existe pas."""
    app.dependency_overrides[get_db] = _sequenced_db(
        [
            ("scalar", legacy_admin_user),  # require_permission
            ("scalar", None),  # rôle introuvable
        ]
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.put(
                f"/api/admin/roles/{uuid.uuid4()}/permissions",
                headers={"Authorization": f"Bearer {token}"},
                json={"permission_codes": []},
            )
        assert res.status_code == 404
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_update_role_permissions_bloque_sans_permission(restricted_admin_user):
    """Un admin sans la permission 'roles.write' ne peut pas modifier les permissions d'un rôle."""
    app.dependency_overrides[get_db] = _sequenced_db(
        [("scalar", restricted_admin_user)]  # require_permission échoue ici
    )
    token = create_access_token(data={"sub": str(restricted_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.put(
                f"/api/admin/roles/{uuid.uuid4()}/permissions",
                headers={"Authorization": f"Bearer {token}"},
                json={"permission_codes": []},
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
