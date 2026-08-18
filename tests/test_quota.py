"""Tests pour le service et les routes de Quotas."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_get_quota_non_existent_user():
    """GET /api/quota/{user_id} doit initialiser et retourner un quota gratuit par défaut."""
    test_user_id = str(uuid.uuid4())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/quota/{test_user_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["statut"] in ["freemium", "premium"]
    assert "restantes" in data
