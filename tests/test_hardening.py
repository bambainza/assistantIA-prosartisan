"""Tests pour le renforcement (Hardening) : CORS, Rate Limiting, Request ID."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_request_id_injected():
    """Vérifie que l'en-tête X-Request-ID est bien généré et retourné dans la réponse."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


@pytest.mark.asyncio
async def test_rate_limiter_blocks_abuse():
    """Vérifie que le Rate Limiter bloque les requêtes trop fréquentes sur les routes sensibles."""
    from app.services.cache_service import cache_service

    cache_service.reset()

    # Configurer temporairement un quota très bas (ex: 2 requêtes max par minute)
    original_limit = settings.rate_limit_requests_per_minute
    settings.rate_limit_requests_per_minute = 2

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Effectuer 3 requêtes consécutives sur une route sensible (/api/chat)
            res1 = await client.post("/api/chat", json={"question": "Test 1"})
            res2 = await client.post("/api/chat", json={"question": "Test 2"})
            res3 = await client.post("/api/chat", json={"question": "Test 3"})

            # Les premières requêtes doivent réussir (ou renvoyer 200/402 selon les quotas de l'utilisateur fictif)
            assert res1.status_code in [200, 402]
            assert res2.status_code in [200, 402]
            # La 3ème requête dépasse la limite de 2 et doit être bloquée avec un code 429
            assert res3.status_code == 429
            assert "Trop de requêtes" in res3.json()["detail"]
    finally:
        # Restaurer la limite d'origine
        settings.rate_limit_requests_per_minute = original_limit


@pytest.mark.asyncio
async def test_cors_headers():
    """Vérifie que les en-têtes CORS sont retournés correctement."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Simuler une requête pré-vol (OPTIONS)
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Requested-With",
        }
        response = await client.options("/health", headers=headers)

    assert response.status_code in [200, 204]
    assert "access-control-allow-origin" in response.headers
