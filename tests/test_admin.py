"""Tests pour le router admin d'ingestion, statistiques et logs (avec authentification)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.user import User


@pytest.fixture
def admin_user():
    return User(
        id=uuid.uuid4(),
        email="admin@test.ci",
        nom="Test Admin",
        is_admin=True,
        type_abonnement="FREE",
    )


@pytest.fixture
def mock_db_with_admin(admin_user):
    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=admin_user))
        )
        yield session
    return custom_mock_db


@pytest.mark.asyncio
async def test_admin_get_stats_unauthorized():
    """GET /api/admin/stats sans token doit retourner 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/admin/stats")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_get_stats_success(mock_db_with_admin, admin_user):
    """GET /api/admin/stats avec token admin valide doit retourner 200."""
    app.dependency_overrides[get_db] = mock_db_with_admin
    token = create_access_token(data={"sub": str(admin_user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/admin/stats", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "collection" in data
        assert "total_chunks" in data
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_admin_get_logs_success(mock_db_with_admin, admin_user):
    """GET /api/admin/logs avec token admin valide doit retourner 200."""
    app.dependency_overrides[get_db] = mock_db_with_admin
    token = create_access_token(data={"sub": str(admin_user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/admin/logs", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
    finally:
        app.dependency_overrides.pop(get_db, None)
