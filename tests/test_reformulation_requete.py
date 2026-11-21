"""Recherche multilingue, réponse de démonstration et repli lexical.

- Une question en nouchi/dioula est aussi cherchée sous une forme reformulée
  en français technique ; la question d'origine reste cherchée et transmise
  au LLM.
- La réponse de démonstration (aucune clé IA) est signalée comme telle et
  n'est jamais mise en cache.
- Le repli lexical (Gemini seul) n'accepte plus un extrait sur un seul mot
  commun.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.services.cache_service import cache_service
from app.services.llm_provider_service import (
    FournisseursIAIndisponiblesError,
    llm_provider_service,
)
from app.services.rag_service import MOCK_REPLY_NOTICE, rag_service

QUESTION_NOUCHI = "Mon vieux, comment on gère dosage pour couler poteau sans gâter ?"
REFORMULEE = "dosage du béton pour poteau en béton armé"

EXTRAIT_A = {
    "content": "Extrait A",
    "metadata": {"document_name": "a.md"},
    "score": 0.7,
}
EXTRAIT_B = {
    "content": "Extrait B",
    "metadata": {"document_name": "b.md"},
    "score": 0.9,
}


@pytest.fixture
def reformulation_active(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    monkeypatch.setattr(settings, "rag_reformulation_requete", True)
    monkeypatch.setattr(settings, "mistral_api_key", "cle-mistral-test")
    completion = AsyncMock(return_value=REFORMULEE)
    monkeypatch.setattr(llm_provider_service, "complete_text_with_failover", completion)
    return completion


@pytest.mark.asyncio
async def test_question_et_reformulation_cherchees_puis_fusionnees(
    monkeypatch, reformulation_active
) -> None:
    requetes: list[str] = []

    async def _search(query: str, metier_id=None, top_k: int = 4):
        requetes.append(query)
        if query == REFORMULEE:
            return [EXTRAIT_B, {**EXTRAIT_A, "score": 0.65}]
        return [EXTRAIT_A]

    monkeypatch.setattr(rag_service, "search_context", _search)
    docs = await rag_service._rechercher(QUESTION_NOUCHI, metier_id=1)

    assert requetes == [QUESTION_NOUCHI, REFORMULEE]
    assert [d["content"] for d in docs] == ["Extrait B", "Extrait A"]
    # Meilleur score conservé pour un extrait trouvé deux fois
    assert docs[1]["score"] == 0.7


@pytest.mark.asyncio
async def test_reformulation_mise_en_cache(reformulation_active) -> None:
    assert await rag_service.reformuler_requete(QUESTION_NOUCHI) == REFORMULEE
    assert await rag_service.reformuler_requete(QUESTION_NOUCHI) == REFORMULEE
    assert reformulation_active.await_count == 1


@pytest.mark.asyncio
async def test_echec_de_reformulation_n_est_pas_une_panne(
    monkeypatch, reformulation_active
) -> None:
    reformulation_active.side_effect = FournisseursIAIndisponiblesError("panne")
    requetes: list[str] = []

    async def _search(query: str, metier_id=None, top_k: int = 4):
        requetes.append(query)
        return [EXTRAIT_A]

    monkeypatch.setattr(rag_service, "search_context", _search)
    docs = await rag_service._rechercher(QUESTION_NOUCHI, metier_id=None)
    assert requetes == [QUESTION_NOUCHI]
    assert docs == [EXTRAIT_A]


@pytest.mark.asyncio
async def test_reformulation_identique_ignoree(reformulation_active) -> None:
    reformulation_active.return_value = "  Quel dosage pour un poteau ?  "
    assert await rag_service.reformuler_requete("quel dosage pour un poteau ?") is None


@pytest.mark.asyncio
async def test_pas_de_reformulation_en_mode_mock(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_reformulation_requete", True)
    completion = AsyncMock()
    monkeypatch.setattr(llm_provider_service, "complete_text_with_failover", completion)
    assert await rag_service.reformuler_requete(QUESTION_NOUCHI) is None
    completion.assert_not_awaited()


@pytest.mark.asyncio
async def test_le_llm_recoit_la_question_d_origine(
    monkeypatch, reformulation_active
) -> None:
    async def _search(query: str, metier_id=None, top_k: int = 4):
        return [EXTRAIT_A]

    async def _actif(_metier_id):
        return True

    monkeypatch.setattr(rag_service, "search_context", _search)
    monkeypatch.setattr(rag_service, "is_metier_active", _actif)
    prep = await rag_service._prepare(QUESTION_NOUCHI, 1, None, None)
    assert prep.messages[-1] == {"role": "user", "content": QUESTION_NOUCHI}


# ── Réponse de démonstration ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reponse_demo_signalee_et_jamais_mise_en_cache(monkeypatch) -> None:
    async def _search(query: str, metier_id=None, top_k: int = 4):
        return [EXTRAIT_A]

    monkeypatch.setattr(rag_service, "search_context", _search)
    cache = AsyncMock()
    monkeypatch.setattr(cache_service, "cache_rag_response", cache)

    res = await rag_service.generate_response(question="Dosage béton poteau ?")
    assert MOCK_REPLY_NOTICE in res["reponse"]
    assert "basée sur les documents" not in res["reponse"]

    _sources, flux = await rag_service.generate_response_stream(
        question="Dosage béton poteau ?"
    )
    texte = "".join([morceau async for morceau in flux])
    assert "Mode démonstration" in texte
    cache.assert_not_awaited()


# ── Repli lexical ────────────────────────────────────────────────────────


def _point(texte: str) -> SimpleNamespace:
    return SimpleNamespace(payload={"text": texte, "document_name": "guide.md"})


@pytest.mark.asyncio
async def test_repli_lexical_refuse_un_seul_mot_commun(monkeypatch) -> None:
    points = [
        _point("Le ciment se stocke au sec sur palette."),
        _point("Dosage du béton de poteau : 350 kg de ciment par m³."),
    ]

    async def _scroll(**_kwargs):
        return points, None

    monkeypatch.setattr(rag_service.qdrant_client, "scroll", _scroll)
    hits = await rag_service._lexical_search_qdrant(
        query="Quel dosage de ciment pour un poteau en béton ?",
        query_filter=None,
        inactive_docs=set(),
        top_k=4,
    )
    assert [h["content"] for h in hits] == [points[1].payload["text"]]
