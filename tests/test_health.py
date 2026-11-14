"""Tests pour la route /health."""

from typing import Any

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


@pytest.mark.parametrize("failure", [None, "db", "redis", "qdrant"])
async def test_readiness_verifie_dependances_sans_details(
    monkeypatch: pytest.MonkeyPatch, failure: Any
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.config import settings
    from app.db.session import get_db
    from app.routers import health

    db = MagicMock()
    db.execute = AsyncMock()
    redis = MagicMock()
    redis.ping = AsyncMock(return_value=True)
    getter = AsyncMock(return_value=redis)
    collection = AsyncMock()
    if failure == "db":
        db.execute.side_effect = RuntimeError("secret-database-password")
    elif failure == "redis":
        getter.return_value = None
    elif failure == "qdrant":
        collection.side_effect = RuntimeError("secret-internal-hostname")

    async def database():
        yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, database)
    monkeypatch.setattr(health.cache_service, "_get_redis", getter)
    monkeypatch.setattr(health.rag_service.qdrant_client, "get_collection", collection)
    monkeypatch.setattr(settings, "build_sha", "tested-commit")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/ready")
        live = await client.get("/api/health")
    assert response.status_code == (503 if failure else 200)
    assert "secret" not in response.text
    assert "version_detail" not in response.text
    assert live.status_code == 200
    if not failure:
        assert response.json()["revision"] == "tested-commit"
        assert str(db.execute.call_args.args[0]) == "SELECT 1"
        redis.ping.assert_awaited_once()
        collection.assert_awaited_once()
