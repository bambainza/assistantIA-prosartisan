"""Tests pour le découpage de documents et le service RAG."""

import pytest

from app.services.rag_service import rag_service
from ingestion.pipeline import chunk_text


def test_chunk_text_overlap():
    """Le découpage sémantique respecte les phrases entières et se chevauche."""
    sample_text = " ".join(f"Phrase numéro {i} du guide technique." for i in range(60))
    chunks = chunk_text(sample_text, chunk_size_words=30, overlap_ratio=0.2)

    assert len(chunks) > 1
    # Une phrase n'est jamais coupée en deux : chaque chunk se termine par un point
    for chunk in chunks:
        assert chunk.strip().endswith(".")

    # Le chevauchement fait apparaître au moins une phrase commune entre deux
    # chunks consécutifs.
    chunk0_sentences = {s.strip() for s in chunks[0].split(".") if s.strip()}
    chunk1_sentences = {s.strip() for s in chunks[1].split(".") if s.strip()}
    assert chunk0_sentences & chunk1_sentences


def test_chunk_text_phrase_trop_longue_reste_entiere():
    """Une phrase plus longue que chunk_size_words forme son propre chunk (jamais tronquée)."""
    phrase_longue = "mot " * 50 + "fin."
    chunks = chunk_text(phrase_longue, chunk_size_words=10, overlap_ratio=0.1)

    assert len(chunks) == 1
    assert chunks[0].strip().endswith("fin.")


def test_chunk_text_texte_vide():
    """Un texte vide (PDF sans texte extractible) ne produit aucun chunk."""
    assert chunk_text("   ") == []


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
