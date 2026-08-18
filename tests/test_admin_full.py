"""Tests complets pour les routes d'administration du Back-Office."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_admin_get_overview():
    """GET /api/admin/overview doit retourner la synthèse des KPIs."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/admin/overview")

    assert response.status_code == 200
    data = response.json()
    assert "kpis" in data
    assert data["kpis"]["total_artisans"] > 0
    assert "abonnements" in data
    assert "metiers_top" in data


@pytest.mark.asyncio
async def test_admin_get_users():
    """GET /api/admin/users doit retourner la liste des artisans."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/admin/users")

    assert response.status_code == 200
    data = response.json()
    assert "users" in data
    assert len(data["users"]) > 0


@pytest.mark.asyncio
async def test_admin_grant_pass():
    """POST /api/admin/users/{id}/grant-pass doit prolonger l'abonnement."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/admin/users/test-id-123/grant-pass?type_pass=pass_mois"
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


@pytest.mark.asyncio
async def test_admin_get_documents():
    """GET /api/admin/documents doit retourner la liste des documents ingérés."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/admin/documents")

    assert response.status_code == 200
    data = response.json()
    assert "documents" in data


@pytest.mark.asyncio
async def test_admin_get_transactions():
    """GET /api/admin/transactions doit retourner l'historique des paiements."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/admin/transactions")

    assert response.status_code == 200
    data = response.json()
    assert "transactions" in data
