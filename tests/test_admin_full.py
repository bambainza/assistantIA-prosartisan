"""Tests complets pour les routes d'administration du Back-Office (avec authentification)."""

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
    )


@pytest.fixture
def mock_db_with_admin(admin_user):
    async def custom_mock_db():
        session = MagicMock()
        
        # Simuler les retours des requêtes ORM dans le routeur admin
        # (ex. get_user pour grant-pass, count pour overview)
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar=MagicMock(return_value=1),
                scalar_one_or_none=MagicMock(return_value=admin_user),
                all=MagicMock(return_value=[])
            )
        )
        session.commit = AsyncMock()
        yield session
    return custom_mock_db


@pytest.mark.asyncio
async def test_admin_get_overview(mock_db_with_admin, admin_user):
    """GET /api/admin/overview doit retourner la synthèse des KPIs avec un token admin."""
    app.dependency_overrides[get_db] = mock_db_with_admin
    token = create_access_token(data={"sub": str(admin_user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/admin/overview", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "kpis" in data
        assert "abonnements" in data
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_admin_get_users(mock_db_with_admin, admin_user):
    """GET /api/admin/users doit retourner la liste des artisans avec un token admin."""
    app.dependency_overrides[get_db] = mock_db_with_admin
    token = create_access_token(data={"sub": str(admin_user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/admin/users", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_admin_grant_pass(mock_db_with_admin, admin_user):
    """POST /api/admin/users/{id}/grant-pass doit prolonger l'abonnement avec un token admin."""
    app.dependency_overrides[get_db] = mock_db_with_admin
    token = create_access_token(data={"sub": str(admin_user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    target_user_id = str(uuid.uuid4())
    
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/admin/users/{target_user_id}/grant-pass?type_pass=pass_mois",
                headers=headers
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_admin_get_documents(mock_db_with_admin, admin_user):
    """GET /api/admin/documents doit retourner la liste des documents avec un token admin."""
    app.dependency_overrides[get_db] = mock_db_with_admin
    token = create_access_token(data={"sub": str(admin_user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/admin/documents", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_admin_get_transactions(mock_db_with_admin, admin_user):
    """GET /api/admin/transactions doit retourner l'historique des paiements avec un token admin."""
    app.dependency_overrides[get_db] = mock_db_with_admin
    token = create_access_token(data={"sub": str(admin_user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/admin/transactions", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
    finally:
        app.dependency_overrides.pop(get_db, None)
