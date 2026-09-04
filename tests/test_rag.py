"""Tests pour le découpage de documents et le service RAG."""

import pytest

from app.config import settings
from app.services.rag_service import FALLBACK_MESSAGE, rag_service
from ingestion.pipeline import chunk_text


class _FakeHit:
    """Simule un point retourné par AsyncQdrantClient.search()."""

    def __init__(self, score: float, payload: dict):
        self.score = score
        self.payload = payload


def test_chunk_text_overlap():
    """Vérifie que le découpage des textes s'effectue avec le bon chevauchement."""
    sample_text = " ".join([f"mot_{i}" for i in range(100)])
    chunks = chunk_text(sample_text, chunk_size=30, overlap=5)

    assert len(chunks) > 1
    # Vérifier que le chevauchement contient des mots communs entre 2 chunks consécutifs
    chunk0_words = set(chunks[0].split())
    chunk1_words = set(chunks[1].split())
    intersection = chunk0_words.intersection(chunk1_words)
    assert len(intersection) >= 5


@pytest.mark.asyncio
async def test_rag_generate_response_mock():
    """Vérifie la génération de réponse par le service RAG."""
    res = await rag_service.generate_response(
        question="Comment faire du mortier de pose pour du carrelage ?",
        metier_id=1,
    )
    assert "reponse" in res
    assert isinstance(res["reponse"], str)
    assert len(res["reponse"]) > 0


@pytest.mark.asyncio
async def test_rag_generate_response_with_history():
    """Vérifie la génération RAG avec un historique conversationnel."""
    history = [
        {"role": "user", "content": "J'ai besoin de conseils pour poser des dalles."},
        {"role": "assistant", "content": "Il faut d'abord égaliser le sol."},
    ]
    res = await rag_service.generate_response(
        question="Quelles dalles choisir ?",
        metier_id=1,
        history=history,
    )
    assert "reponse" in res
    assert isinstance(res["reponse"], str)
    assert len(res["reponse"]) > 0
    assert "sources" in res

    # Vérifier que le mode stream retourne aussi sources et générateur
    sources, _gen = await rag_service.generate_response_stream(
        question="Quelles dalles choisir ?",
        metier_id=1,
        history=history,
    )
    assert isinstance(sources, list)


@pytest.mark.asyncio
async def test_search_context_filtre_les_extraits_hors_sujet(monkeypatch):
    """Un extrait sous le score minimal est écarté (garde-fou zéro hallucination)."""

    async def fake_search(**_kwargs):
        return [
            _FakeHit(score=0.02, payload={"text": "hors sujet"}),
            _FakeHit(score=0.9, payload={"text": "pertinent"}),
        ]

    monkeypatch.setattr(rag_service.qdrant_client, "search", fake_search)

    docs = await rag_service.search_context(query="dosage béton", metier_id=1)

    assert len(docs) == 1
    assert docs[0]["content"] == "pertinent"


@pytest.mark.asyncio
async def test_generate_response_repli_sans_contexte(monkeypatch):
    """Sans extrait pertinent et sans photo, la réponse est le repli standard (pas le LLM)."""

    async def fake_search_context(**_kwargs):
        return []

    monkeypatch.setattr(rag_service, "search_context", fake_search_context)

    res = await rag_service.generate_response(
        question="Question totalement hors du périmètre métier"
    )

    assert res["reponse"] == FALLBACK_MESSAGE
    assert res["sources"] == []


@pytest.mark.asyncio
async def test_generate_response_stream_repli_sans_contexte(monkeypatch):
    """Le flux SSE renvoie aussi le message de repli, sans appeler le LLM."""

    async def fake_search_context(**_kwargs):
        return []

    monkeypatch.setattr(rag_service, "search_context", fake_search_context)

    sources, generator = await rag_service.generate_response_stream(
        question="Question totalement hors du périmètre métier"
    )

    chunks = [chunk async for chunk in generator]
    assert sources == []
    assert "".join(chunks).strip() == FALLBACK_MESSAGE


@pytest.mark.asyncio
async def test_generate_response_avec_image_ignore_le_repli(monkeypatch):
    """Une question avec photo n'est jamais bloquée par le repli, même sans document."""

    async def fake_search_context(**_kwargs):
        return []

    monkeypatch.setattr(rag_service, "search_context", fake_search_context)

    res = await rag_service.generate_response(
        question="Cette fissure est-elle dangereuse ?",
        image_url="https://example.com/fissure.jpg",
    )

    assert res["reponse"] != FALLBACK_MESSAGE


@pytest.mark.asyncio
async def test_ensure_collection_la_cree_si_absente(monkeypatch):
    """ensure_collection() crée la collection Qdrant quand elle n'existe pas."""
    appels: dict = {}

    async def fake_exists(_name):
        return False

    async def fake_create(**kwargs):
        appels.update(kwargs)

    monkeypatch.setattr(rag_service.qdrant_client, "collection_exists", fake_exists)
    monkeypatch.setattr(rag_service.qdrant_client, "create_collection", fake_create)

    await rag_service.ensure_collection()

    assert appels["collection_name"] == settings.qdrant_collection
    assert appels["vectors_config"].size == settings.qdrant_vector_size


@pytest.mark.asyncio
async def test_ensure_collection_ne_recree_pas_si_presente(monkeypatch):
    """ensure_collection() ne fait rien si la collection existe déjà."""
    appels: list = []

    async def fake_exists(_name):
        return True

    async def fake_create(**kwargs):
        appels.append(kwargs)

    monkeypatch.setattr(rag_service.qdrant_client, "collection_exists", fake_exists)
    monkeypatch.setattr(rag_service.qdrant_client, "create_collection", fake_create)

    await rag_service.ensure_collection()

    assert appels == []
