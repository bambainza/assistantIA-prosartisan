"""Tests pour le découpage de documents et le service RAG."""

import pytest

from app.services.rag_service import rag_service
from ingestion.pipeline import chunk_text


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
        {"role": "assistant", "content": "Il faut d'abord égaliser le sol."}
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

