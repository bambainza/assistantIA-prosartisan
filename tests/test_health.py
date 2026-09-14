"""Tests pour la route /health."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok():
    """GET /health et GET /api/health doivent retourner status=ok."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "ProsArtisan IA Expert"

        # Vérifier également le chemin /api/health requis par Docker / Cloud Run
        api_response = await client.get("/api/health")
        assert api_response.status_code == 200
        assert api_response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_root_returns_welcome():
    """GET / doit retourner le message de bienvenue."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert "ProsArtisan" in data["message"]
