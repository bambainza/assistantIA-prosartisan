"""Tests pour le CacheService (hybride Redis / in-memory)."""

import pytest

from app.services.cache_service import CacheService
from app.services.rag_service import rag_service


@pytest.mark.asyncio
async def test_cache_service_in_memory_set_get():
    """Vérifie que le fallback en mémoire stocke et restitue correctement une valeur."""
    cache = CacheService()
    cache._redis_available = False  # Forcer le mode mémoire

    await cache.set("test:cle", "valeur_chantier", ttl_seconds=10)
    result = await cache.get("test:cle")
    assert result == "valeur_chantier"

    # Clé inexistante
    not_found = await cache.get("test:inexistante")
    assert not_found is None


@pytest.mark.asyncio
async def test_cache_service_ttl_expiration():
    """Vérifie qu'une clé expirée n'est plus retournée."""
    cache = CacheService()
    cache._redis_available = False

    # TTL négatif pour forcer l'expiration immédiate
    await cache.set("test:expired", "expire_vite", ttl_seconds=-1)
    result = await cache.get("test:expired")
    assert result is None


@pytest.mark.asyncio
async def test_cache_service_embeddings():
    """Vérifie la sérialisation / désérialisation des embeddings vectoriels."""
    cache = CacheService()
    cache._redis_available = False

    text = "Dosage mortier pour chape"
    vector = [0.123, 0.456, -0.789]

    await cache.cache_embedding(text, vector)
    cached_vec = await cache.get_cached_embedding(text)
    assert cached_vec == vector

    # Différence de casse / espaces gérée par le hachage
    cached_vec_spaced = await cache.get_cached_embedding("  dosage mortier pour chape ")
    assert cached_vec_spaced == vector


@pytest.mark.asyncio
async def test_cache_service_rag_response():
    """Vérifie la mise en cache et restitution d'une réponse RAG."""
    cache = CacheService()
    cache._redis_available = False

    question = "Quelle épaisseur minimale pour un carrelage extérieur ?"
    dummy_res = {
        "reponse": "L'épaisseur minimale conseillée est de 20 mm.",
        "sources": [{"metier_id": 1, "doc": "fiche_carrelage.pdf"}],
    }

    await cache.cache_rag_response(question=question, metier_id=1, response=dummy_res)
    cached = await cache.get_cached_rag_response(question=question, metier_id=1)
    assert cached is not None
    assert cached["reponse"] == dummy_res["reponse"]
    assert len(cached["sources"]) == 1


@pytest.mark.asyncio
async def test_rag_service_uses_cache():
    """Vérifie que RAGService interroge et renseigne le cache."""
    question = "Question test cache RAG récurrente"
    # Premier appel -> calcul et mise en cache
    res1 = await rag_service.generate_response(question=question, metier_id=1)
    assert "reponse" in res1

    # Second appel -> doit provenir du cache
    res2 = await rag_service.generate_response(question=question, metier_id=1)
    assert res2["reponse"] == res1["reponse"]
