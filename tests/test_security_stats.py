"""Tests pour le dashboard sécurité enrichi (GET /api/admin/security-stats)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.user import User
from tests.conftest import mock_get_db


@pytest.fixture
def legacy_admin_user():
    return User(
        id=uuid.uuid4(),
        email="secstats_admin@prosartisan.ci",
        nom="Admin Sécurité",
        telephone="+22507000050",
        is_admin=True,
        role_id=None,
    )


@pytest.mark.asyncio
async def test_security_stats_retourne_les_compteurs(legacy_admin_user):
    """GET /api/admin/security-stats agrège audit 24h + compteurs Redis/mémoire."""

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=legacy_admin_user),
                scalar=MagicMock(return_value=7),
            )
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/admin/security-stats",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 200
        data = res.json()
        assert data["actions_admin_dernieres_24h"] == 7
        assert "tentatives_connexion_echouees_30j" in data
        assert "webhooks_rejetes_30j" in data
        assert "tokens_revoques_30j" in data
    finally:
        app.dependency_overrides[get_db] = mock_get_db
