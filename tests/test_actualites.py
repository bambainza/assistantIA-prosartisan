"""Tests pour le module Actualités (public + back-office).

Régression sécurité : les mutations (création, publication, suppression)
exigent la permission `actualites.write` — sans `require_permission`, un
admin disposant d'un rôle restreint pourrait publier du contenu hors de son
périmètre.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.actualite import Actualite
from app.models.role import Permission, Role
from app.models.user import User
from tests.conftest import mock_get_db


@pytest.fixture
def legacy_admin_user():
    return User(
        id=uuid.uuid4(),
        email="actu_admin@prosartisan.ci",
        nom="Admin Actualités",
        telephone="+22507000030",
        is_admin=True,
        role_id=None,
    )


@pytest.fixture
def restricted_admin_no_actualites():
    """Admin avec un rôle RBAC qui n'accorde PAS `actualites.write`."""
    role = Role(id=uuid.uuid4(), code="support", label="Support Client")
    role.permissions = [Permission(id=uuid.uuid4(), code="packages.read")]
    user = User(
        id=uuid.uuid4(),
        email="support_no_actu@prosartisan.ci",
        nom="Admin Support",
        telephone="+22507000031",
        is_admin=True,
    )
    user.role = role
    return user


@pytest.fixture
def sample_actualite():
    return Actualite(
        id=uuid.uuid4(),
        titre="Nouveau guide dosage béton",
        contenu="Un nouveau guide DTU 20.1 est disponible pour la maçonnerie.",
        metier_id=1,
        statut="brouillon",
        publie_at=None,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


@pytest.mark.asyncio
async def test_liste_publique_actualites():
    """GET /api/actualites (public, sans authentification) retourne les actualités publiées."""
    published = Actualite(
        id=uuid.uuid4(),
        titre="Conseil saisonnier",
        contenu="Attention aux fortes pluies pour le séchage du ciment.",
        metier_id=None,
        statut="publie",
        publie_at=datetime.now(UTC).replace(tzinfo=None),
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[published]))
                )
            )
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/actualites")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["titre"] == "Conseil saisonnier"
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_creation_actualite_refuse_sans_permission(
    restricted_admin_no_actualites,
):
    """Un admin sans la permission 'actualites.write' ne peut pas créer d'actualité."""

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(
                    return_value=restricted_admin_no_actualites
                )
            )
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(restricted_admin_no_actualites.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/admin/actualites",
                headers={"Authorization": f"Bearer {token}"},
                json={"titre": "Test", "contenu": "Contenu de test"},
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_creation_actualite_succes(legacy_admin_user):
    """Un admin avec accès complet peut créer une actualité (statut brouillon par défaut)."""

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=legacy_admin_user)
            )
        )
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/admin/actualites",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "titre": "Nouveau guide plomberie",
                    "contenu": "Guide DTU 60.1 mis à jour.",
                    "metier_id": 3,
                },
            )
        assert res.status_code == 201
        data = res.json()
        assert data["titre"] == "Nouveau guide plomberie"
        assert data["statut"] == "brouillon"
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_publication_actualite_avec_notification(
    legacy_admin_user, sample_actualite
):
    """La publication avec notification programme une tâche de fond sans bloquer la réponse."""
    # Ordre des requêtes synchrones : (1) require_permission fetch l'admin,
    # (2) actualite_service.get() récupère l'actualité, (3) target_user_ids()
    # liste les IDs à notifier (résultat consommé via .all(), pas scalar_one_or_none).
    call_index = {"n": 0}

    async def custom_mock_db():
        session = MagicMock()

        async def mock_execute(stmt):
            mock_res = MagicMock()
            call_index["n"] += 1
            if call_index["n"] == 1:
                mock_res.scalar_one_or_none.return_value = legacy_admin_user
            elif call_index["n"] == 2:
                mock_res.scalar_one_or_none.return_value = sample_actualite
            else:
                mock_res.all.return_value = []
            return mock_res

        session.execute = mock_execute
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/actualites/{sample_actualite.id}/publish",
                headers={"Authorization": f"Bearer {token}"},
                json={"notifier_artisans": True},
            )
        assert res.status_code == 200
        assert res.json()["statut"] == "publie"
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_suppression_actualite_refuse_sans_permission(
    restricted_admin_no_actualites,
):
    """Un admin sans 'actualites.write' ne peut pas supprimer une actualité."""

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(
                    return_value=restricted_admin_no_actualites
                )
            )
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(restricted_admin_no_actualites.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.delete(
                f"/api/admin/actualites/{uuid.uuid4()}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db
