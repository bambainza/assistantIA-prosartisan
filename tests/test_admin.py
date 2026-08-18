"""Tests pour le router admin d'ingestion et statistiques."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_admin_get_stats():
    """GET /api/admin/stats doit retourner les statistiques de Qdrant."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/admin/stats")

    assert response.status_code == 200
    data = response.json()
    assert "collection" in data
    assert "metiers_coverts" in data


@pytest.mark.asyncio
async def test_admin_get_logs():
    """GET /api/admin/logs doit retourner les journaux d'événements."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/admin/logs")

    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
