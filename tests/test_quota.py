"""Tests pour le service et les routes de Quotas."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.middleware.auth import create_access_token


@pytest.mark.asyncio
async def test_get_quota_utilisateur_authentifie():
    """GET /api/quota (authentifié) initialise et retourne le quota gratuit de l'utilisateur du JWT."""
    token = create_access_token(data={"sub": str(uuid.uuid4())})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/quota", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["statut"] in ["freemium", "premium"]
    assert "restantes" in data


@pytest.mark.asyncio
async def test_get_quota_anonyme():
    """GET /api/quota sans authentification retourne le quota du compte anonyme partagé."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/quota")

    assert response.status_code == 200
    data = response.json()
    assert data["statut"] in ["freemium", "premium"]


@pytest.mark.asyncio
async def test_get_quota_user_id_dans_le_chemin_nexiste_plus():
    """L'ancienne route /api/quota/{user_id} (usurpable) a été retirée."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/quota/{uuid.uuid4()}")

    assert response.status_code == 404
