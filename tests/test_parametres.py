"""Tests pour le module Paramètres (back-office admin) : CRUD des données de
référence (métiers, sous-métiers, catégories d'actualités) qui alimentent les
listes de choix ailleurs dans l'admin.

Régression sécurité : sans `require_permission`, un admin restreint pourrait
créer/modifier/supprimer une donnée de référence sans détenir
`parametres.read`/`parametres.write` — ces tests échoueraient sans le
garde-fou de app.middleware.auth.require_permission.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.actualite import ActualiteCategorie
from app.models.metier import Metier
from app.models.role import Permission, Role
from app.models.user import User
from tests.conftest import mock_get_db


@pytest.fixture
def legacy_admin_user():
    """Admin historique (is_admin=True) sans rôle RBAC : accès complet hérité."""
    return User(
        id=uuid.uuid4(),
        email="legacy_admin_parametres@prosartisan.ci",
        nom="Admin Historique",
        is_admin=True,
        role_id=None,
    )


@pytest.fixture
def restricted_admin_user():
    """Admin avec un rôle RBAC ne donnant accès à rien du module Paramètres."""
    role = Role(id=uuid.uuid4(), code="autre_role", label="Autre rôle")
    role.permissions = [Permission(id=uuid.uuid4(), code="actualites.read")]
    user = User(
        id=uuid.uuid4(),
        email="restricted_parametres@prosartisan.ci",
        nom="Admin Restreint",
        is_admin=True,
    )
    user.role = role
    return user


def _mock_db(responses, *, commit_raises: Exception | None = None):
    """Mock DB : chaque appel `db.execute` consomme la réponse suivante de
    `responses` (tuples `("scalar", valeur)` ou `("rows", [..])`).

    `db.refresh` simule l'affectation de la clé primaire par la base (auto-
    increment, jamais connue avant un vrai flush/commit) en assignant un id
    à tout objet qui n'en a pas encore.
    """

    async def custom_mock_db():
        session = MagicMock()
        queue = list(responses)

        async def mock_execute(stmt):
            kind, value = queue.pop(0)
            mock_res = MagicMock()
            if kind == "scalar":
                mock_res.scalar_one_or_none.return_value = value
                mock_res.scalar.return_value = value
            else:
                mock_res.all.return_value = value
                mock_res.scalars.return_value.all.return_value = value
            return mock_res

        session.execute = mock_execute
        session.add = MagicMock()
        session.delete = AsyncMock()
        session.rollback = AsyncMock()

        if commit_raises is not None:

            async def mock_commit():
                raise commit_raises

            session.commit = mock_commit
        else:
            session.commit = AsyncMock()

        async def mock_refresh(obj):
            if getattr(obj, "id", None) is None:
                obj.id = 999

        session.refresh = mock_refresh
        yield session

    return custom_mock_db


@pytest.mark.asyncio
async def test_list_metiers_bloque_sans_permission(restricted_admin_user):
    """Un admin sans 'parametres.read' ne peut pas consulter les métiers de référence."""
    app.dependency_overrides[get_db] = _mock_db([("scalar", restricted_admin_user)])
    token = create_access_token(data={"sub": str(restricted_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/admin/parametres/metiers",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_create_metier_bloque_sans_permission(restricted_admin_user):
    """Un admin sans 'parametres.write' ne peut pas créer de métier."""
    app.dependency_overrides[get_db] = _mock_db([("scalar", restricted_admin_user)])
    token = create_access_token(data={"sub": str(restricted_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/admin/parametres/metiers",
                headers={"Authorization": f"Bearer {token}"},
                json={"nom": "Test", "slug": "test"},
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_create_metier_success(legacy_admin_user):
    """Un admin avec accès complet peut créer un métier de référence."""
    app.dependency_overrides[get_db] = _mock_db([("scalar", legacy_admin_user)])
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/admin/parametres/metiers",
                headers={"Authorization": f"Bearer {token}"},
                json={"nom": "Nouveau Métier", "slug": "nouveau-metier"},
            )
        assert res.status_code == 201
        body = res.json()
        assert body["nom"] == "Nouveau Métier"
        assert body["slug"] == "nouveau-metier"
        assert body["is_active"] is True
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_create_metier_slug_duplique_conflit(legacy_admin_user):
    """Un slug déjà utilisé doit échouer avec 409, pas une erreur serveur brute."""
    app.dependency_overrides[get_db] = _mock_db(
        [("scalar", legacy_admin_user)],
        commit_raises=IntegrityError("INSERT", {}, Exception("duplicate key")),
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/admin/parametres/metiers",
                headers={"Authorization": f"Bearer {token}"},
                json={"nom": "Doublon", "slug": "batiment-construction"},
            )
        assert res.status_code == 409
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_delete_metier_encore_utilise_conflit(legacy_admin_user):
    """Supprimer un métier encore référencé (FK RESTRICT) doit échouer avec 409."""
    metier = Metier(id=7, nom="Bâtiment", slug="batiment", is_active=True)
    app.dependency_overrides[get_db] = _mock_db(
        [("scalar", legacy_admin_user), ("scalar", metier)],
        commit_raises=IntegrityError("DELETE", {}, Exception("fk violation")),
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.delete(
                "/api/admin/parametres/metiers/7",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 409
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_toggle_metier_success(legacy_admin_user):
    """Un admin avec accès complet peut activer/désactiver un métier."""
    metier = Metier(id=3, nom="Plomberie", slug="plomberie", is_active=True)
    app.dependency_overrides[get_db] = _mock_db(
        [("scalar", legacy_admin_user), ("scalar", metier)]
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.patch(
                "/api/admin/parametres/metiers/3/toggle",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 200
        assert res.json()["is_active"] is False
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_create_categorie_bloque_sans_permission(restricted_admin_user):
    """Un admin sans 'parametres.write' ne peut pas créer de catégorie d'actualité."""
    app.dependency_overrides[get_db] = _mock_db([("scalar", restricted_admin_user)])
    token = create_access_token(data={"sub": str(restricted_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/admin/parametres/actualite-categories",
                headers={"Authorization": f"Bearer {token}"},
                json={"code": "evenement", "label": "Événement"},
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_create_categorie_success(legacy_admin_user):
    """Un admin avec accès complet peut créer une catégorie d'actualité."""
    app.dependency_overrides[get_db] = _mock_db([("scalar", legacy_admin_user)])
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/admin/parametres/actualite-categories",
                headers={"Authorization": f"Bearer {token}"},
                json={"code": "evenement", "label": "Événement"},
            )
        assert res.status_code == 201
        body = res.json()
        assert body["code"] == "evenement"
        assert body["label"] == "Événement"
        assert body["is_active"] is True
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_delete_categorie_success(legacy_admin_user):
    """Un admin avec accès complet peut supprimer une catégorie d'actualité."""
    categorie = ActualiteCategorie(id=5, code="promo_test", label="Promo Test")
    app.dependency_overrides[get_db] = _mock_db(
        [("scalar", legacy_admin_user), ("scalar", categorie)]
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.delete(
                "/api/admin/parametres/actualite-categories/5",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 200
    finally:
        app.dependency_overrides[get_db] = mock_get_db
