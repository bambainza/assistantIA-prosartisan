"""Tests d'évaluation de la robustesse RAG multilingue (Nouchi, Dioula, Baoulé) et zéro-hallucination."""

import pytest

from app.services.rag_service import FALLBACK_MESSAGE, rag_service


@pytest.fixture
def mock_qdrant_context(monkeypatch):
    """Fournit un contexte documentaire simulé pour tester la synthèse RAG sans dépendance réseau."""

    async def _mock_search(query: str, metier_id: int | None = None, top_k: int = 4):
        return [
            {
                "content": (
                    f"Règles techniques de référence pour le métier {metier_id} :\n"
                    "1. Dosage du béton pour poteaux et dalles : 350 kg/m³ de ciment CPJ 42.5.\n"
                    "2. Enrobage des aciers HA : 3 cm en intérieur, 5 cm en zone lagunaire.\n"
                    "3. Hygiène et chaîne du froid : maintien des denrées entre 0°C et +3°C.\n"
                    "4. Motos utilitaires : réglage vis de richesse à 1.5 - 2 tours."
                ),
                "metadata": {
                    "document_name": f"guide_technique_metier_{metier_id}.md",
                    "metier_id": metier_id,
                },
                "score": 0.88,
            }
        ]

    monkeypatch.setattr(rag_service, "search_context", _mock_search)


@pytest.mark.asyncio
async def test_rag_nouchi_maconnerie_dosage(mock_qdrant_context):
    """Vérifie la prise en charge d'une formulation en Nouchi de chantier pour le BTP."""
    # Nouchi ivoirien de chantier : "Mon vieux père / boss, comment on gère le bon dosage ciment pour couler poteau sans gâter ?"
    question = "Mon vieux père, donne moi le bon dosage de ciment pour couler poteau sans que ça se gâte."
    res = await rag_service.generate_response(question=question, metier_id=1)

    assert "reponse" in res
    assert isinstance(res["reponse"], str)
    assert len(res["reponse"]) > 0
    assert "Points clés techniques" in res["reponse"] or "350 kg/m³" in res["reponse"]
    assert len(res["sources"]) > 0


@pytest.mark.asyncio
async def test_rag_nouchi_electricite_panne(mock_qdrant_context):
    """Vérifie une question en Nouchi sur une disjonction électrique ('coupe-décaler')."""
    question = "Le courant fait coupe-décaler sur mon disjoncteur différentiel dès que j'allume le moteur, c'est quoi le problème ?"
    res = await rag_service.generate_response(question=question, metier_id=2)

    assert "reponse" in res
    assert len(res["reponse"]) > 0
    assert len(res["sources"]) > 0


@pytest.mark.asyncio
async def test_rag_mecanique_motos_jakarta(mock_qdrant_context):
    """Vérifie une question sur la mécanique motos et tricycles utilitaires."""
    question = "Ma moto Jakarta cale à chaud quand j'accélère fort, comment régler la vis de richesse du carburateur ?"
    res = await rag_service.generate_response(question=question, metier_id=4)

    assert "reponse" in res
    assert len(res["reponse"]) > 0
    assert len(res["sources"]) > 0


@pytest.mark.asyncio
async def test_rag_restauration_maquis_hygiene(mock_qdrant_context):
    """Vérifie une question sur les métiers de bouche / maquis."""
    question = "Dans mon maquis, comment désinfecter les crudités et la tomate pour l'alloco et le garba sans risque pour les clients ?"
    res = await rag_service.generate_response(question=question, metier_id=5)

    assert "reponse" in res
    assert len(res["reponse"]) > 0
    assert len(res["sources"]) > 0


@pytest.mark.asyncio
async def test_rag_maroquinerie_couture_sellier(mock_qdrant_context):
    """Vérifie une question sur la maroquinerie d'art et travail du cuir."""
    question = "Quel fil utiliser pour la couture sellier à deux aiguilles sur cuir épais de tannage végétal ?"
    res = await rag_service.generate_response(question=question, metier_id=6)

    assert "reponse" in res
    assert len(res["reponse"]) > 0
    assert len(res["sources"]) > 0


@pytest.mark.asyncio
async def test_rag_termes_dioula_et_baoule(mock_qdrant_context):
    """Vérifie la robustesse avec des termes locaux intégrés (ex: dji = eau en dioula, wari = argent/devis)."""
    question = "Mon dji d'évacuation fuit sous la dalle, comment coller le tuyau PVC pression ?"
    res = await rag_service.generate_response(question=question, metier_id=3)

    assert "reponse" in res
    assert len(res["reponse"]) > 0
    assert len(res["sources"]) > 0


@pytest.mark.asyncio
async def test_rag_zero_hallucination_hors_sujet_strict(monkeypatch):
    """Vérifie que le RAG renvoie strictement le message de fallback sans documents pertinents.

    Garde-fou AGENTS.md §3 : si aucun extrait pertinent n'est trouvé, le LLM n'est pas appelé
    et le message de repli codé en dur est retourné.
    """

    async def mock_empty_search(*args, **kwargs):
        return []

    monkeypatch.setattr(rag_service, "search_context", mock_empty_search)

    res = await rag_service.generate_response(
        question="Comment programmer un satellite géostationnaire en langage Rust ?",
        metier_id=1,
    )

    assert res["reponse"] == FALLBACK_MESSAGE
    assert res["sources"] == []
