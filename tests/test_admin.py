"""Tests pour le router admin d'ingestion, statistiques et logs (avec authentification)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.metier import Metier
from app.models.user import User
from app.routers.admin.contenus import (
    _scroll_all_qdrant_points,
    get_ingestion_stats,
)


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
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=admin_user)
            )
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
async def test_admin_get_stats_success(mock_db_with_admin, admin_user, admin_qdrant):
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
        assert data["total_chunks"] == 0
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_stats_qdrant_agregent_documents_par_metier(admin_qdrant):
    admin_qdrant.points = [
        MagicMock(payload={"document_name": "a.md", "metier_id": 7}),
        MagicMock(payload={"document_name": "a.md", "metier_id": 7}),
        MagicMock(payload={"document_name": "b.md", "metier_id": 7}),
    ]
    admin_qdrant.points_count = 3
    db = MagicMock()
    metier = Metier(id=7, nom="Menuiserie", slug="menuiserie")
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[metier]))
            )
        )
    )

    data = await get_ingestion_stats(admin_id=uuid.uuid4(), db=db)

    assert data["total_chunks"] == 3
    assert data["metiers_coverts"] == [
        {"metier_id": 7, "nom": "Menuiserie", "documents_ingeres": 2}
    ]


@pytest.mark.asyncio
async def test_scroll_qdrant_parcourt_toutes_les_pages():
    client = MagicMock()
    client.scroll = AsyncMock(
        side_effect=[
            ([MagicMock(id=1)], "page-2"),
            ([MagicMock(id=2)], None),
        ]
    )

    points = await _scroll_all_qdrant_points(client)

    assert [point.id for point in points] == [1, 2]
    assert client.scroll.await_count == 2
    assert client.scroll.await_args_list[1].kwargs["offset"] == "page-2"


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
