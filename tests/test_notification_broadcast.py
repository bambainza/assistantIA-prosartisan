"""Tests pour le centre de diffusion de notifications (composer admin).

Régression sécurité : `POST /api/admin/notifications/broadcast` exige la
permission `notifications.send` — sans `require_permission`, n'importe quel
compte admin pourrait spammer l'ensemble des artisans.
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
    return User(
        id=uuid.uuid4(),
        email="broadcast_admin@prosartisan.ci",
        nom="Admin Diffusion",
        telephone="+22507000040",
        is_admin=True,
        role_id=None,
    )


@pytest.fixture
def restricted_admin_no_broadcast():
    role = Role(id=uuid.uuid4(), code="moderateur_contenu", label="Modérateur")
    role.permissions = [Permission(id=uuid.uuid4(), code="documents.write")]
    user = User(
        id=uuid.uuid4(),
        email="moderateur_no_broadcast@prosartisan.ci",
        nom="Admin Modérateur",
        telephone="+22507000041",
        is_admin=True,
    )
    user.role = role
    return user


@pytest.mark.asyncio
async def test_broadcast_refuse_sans_permission(restricted_admin_no_broadcast):
    """Un admin sans la permission 'notifications.send' ne peut pas diffuser."""

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=restricted_admin_no_broadcast)
            )
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(restricted_admin_no_broadcast.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/admin/notifications/broadcast",
                headers={"Authorization": f"Bearer {token}"},
                json={"title": "Alerte", "body": "Test"},
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_broadcast_succes_admin_historique(legacy_admin_user):
    """Un admin avec accès complet peut composer et diffuser une notification (202 immédiat)."""
    target_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    call_index = {"n": 0}

    async def custom_mock_db():
        session = MagicMock()

        async def mock_execute(stmt):
            mock_res = MagicMock()
            call_index["n"] += 1
            if call_index["n"] == 1:
                mock_res.scalar_one_or_none.return_value = legacy_admin_user
            else:
                mock_res.all.return_value = [(uid,) for uid in target_ids]
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
                "/api/admin/notifications/broadcast",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "title": "Nouvelle formule disponible",
                    "body": "Découvrez le Pass Annuel Excellence.",
                    "metier_id": 1,
                },
            )
        assert res.status_code == 202
        data = res.json()
        assert data["status"] == "accepted"
        assert data["cible_count"] == 3
    finally:
        app.dependency_overrides[get_db] = mock_get_db
