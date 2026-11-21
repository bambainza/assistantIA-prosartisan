"""Recherche documentaire avec les vecteurs Gemini (`gemini-embedding-001`).

- Appel `batchEmbedContents` : modèle, dimension, `taskType` question/document.
- Cache et collection Qdrant propres au modèle : jamais de vecteur d'un autre
  modèle relu ou interrogé.
- Manifeste d'ingestion par collection : changer de modèle réindexe tout.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.services.llm_provider_service import llm_provider_service
from app.services.rag_service import TACHE_DOCUMENT, TACHE_REQUETE, rag_service
from ingestion.pipeline import run_ingestion

DIM = 1536


def _reponse_vecteurs(requete: httpx.Request, valeur: float = 0.5) -> httpx.Response:
    corps = json.loads(requete.content)
    return httpx.Response(
        200,
        json={"embeddings": [{"values": [valeur] * DIM} for _ in corps["requests"]]},
    )


@pytest.fixture
def gemini_vecteurs(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Vecteurs Gemini simulés ; retourne les corps de requête reçus."""
    monkeypatch.setattr(settings, "embedding_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-cle-gemini-test")
    monkeypatch.setattr(settings, "gemini_embedding_model", "gemini-embedding-001")
    monkeypatch.setattr(settings, "gemini_embedding_dimensions", DIM)
    recues: list[dict] = []

    def _handler(requete: httpx.Request) -> httpx.Response:
        assert requete.url.path.endswith(
            "/models/gemini-embedding-001:batchEmbedContents"
        )
        assert requete.headers["x-goog-api-key"] == "AIza-cle-gemini-test"
        recues.append(json.loads(requete.content))
        return _reponse_vecteurs(requete)

    monkeypatch.setattr(
        llm_provider_service, "_http_transport", httpx.MockTransport(_handler)
    )
    return recues


# ── Configuration ────────────────────────────────────────────────────────


def test_collection_par_modele_de_vecteurs() -> None:
    gemini = Settings(_env_file=None, embedding_provider="gemini")
    assert gemini.collection_vectorielle == "connaissances_prosartisan_gemini_1536"
    assert gemini.embedding_dimensions == 1536
    mistral = Settings(_env_file=None, embedding_provider="Mistral")
    # Mistral garde le nom historique (déploiements existants)
    assert mistral.collection_vectorielle == "connaissances_prosartisan"
    assert mistral.embedding_dimensions == 1024
    assert Settings(_env_file=None).embedding_provider == "gemini"


@pytest.mark.parametrize(
    "valeurs",
    [{"embedding_provider": "openai"}, {"gemini_embedding_dimensions": 1024}],
)
def test_configuration_de_vecteurs_invalide_refusee(valeurs: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **valeurs)


# ── Appel batchEmbedContents ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_requete_batch_embed_contents(gemini_vecteurs) -> None:
    vecteurs = await llm_provider_service.embed_gemini(
        ["dosage béton", "pente PVC"], task_type="RETRIEVAL_DOCUMENT"
    )
    assert len(vecteurs) == 2 and len(vecteurs[0]) == DIM
    (corps,) = gemini_vecteurs
    premiere = corps["requests"][0]
    assert premiere["model"] == "models/gemini-embedding-001"
    assert premiere["taskType"] == "RETRIEVAL_DOCUMENT"
    assert premiere["outputDimensionality"] == DIM
    assert premiere["content"] == {"parts": [{"text": "dosage béton"}]}


@pytest.mark.asyncio
async def test_gemini_embedding_2_sans_task_type(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gemini_embedding_model", "gemini-embedding-2")
    monkeypatch.setattr(settings, "gemini_embedding_dimensions", DIM)
    recues: list[dict] = []

    def _handler(requete: httpx.Request) -> httpx.Response:
        recues.append(json.loads(requete.content))
        return _reponse_vecteurs(requete)

    monkeypatch.setattr(
        llm_provider_service, "_http_transport", httpx.MockTransport(_handler)
    )
    await llm_provider_service.embed_gemini(["x"], task_type="RETRIEVAL_QUERY")
    assert "taskType" not in recues[0]["requests"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reponse",
    [
        httpx.Response(429, text="quota"),
        httpx.Response(200, json={"embeddings": [{"values": [0.1] * 10}]}),
        httpx.Response(200, json={"embeddings": []}),
    ],
)
async def test_reponse_de_vecteurs_invalide_levee(monkeypatch, reponse) -> None:
    monkeypatch.setattr(settings, "gemini_embedding_dimensions", DIM)
    monkeypatch.setattr(
        llm_provider_service,
        "_http_transport",
        httpx.MockTransport(lambda _r: reponse),
    )
    with pytest.raises(RuntimeError):
        await llm_provider_service.embed_gemini(["x"], task_type="RETRIEVAL_QUERY")


# ── Service RAG ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_question_et_document_encodes_et_mis_en_cache_separement(
    gemini_vecteurs,
) -> None:
    await rag_service.get_embedding("dosage béton poteau", tache=TACHE_REQUETE)
    await rag_service.get_embeddings(["dosage béton poteau"], tache=TACHE_DOCUMENT)
    await rag_service.get_embedding("dosage béton poteau", tache=TACHE_REQUETE)

    taches = [c["requests"][0]["taskType"] for c in gemini_vecteurs]
    # Deux appels (question puis document), le troisième vient du cache
    assert taches == ["RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT"]


@pytest.mark.asyncio
async def test_vecteur_mistral_en_cache_jamais_relu_par_gemini(
    monkeypatch, gemini_vecteurs
) -> None:
    from app.services.cache_service import cache_service

    monkeypatch.setattr(settings, "embedding_provider", "mistral")
    await cache_service.cache_embedding(
        "pente PVC", [9.9] * 1024, espace=settings.espace_embeddings
    )
    monkeypatch.setattr(settings, "embedding_provider", "gemini")

    vecteur = await rag_service.get_embedding("pente PVC")
    assert len(vecteur) == DIM and len(gemini_vecteurs) == 1


@pytest.mark.asyncio
async def test_recherche_interroge_la_collection_gemini(
    monkeypatch, gemini_vecteurs
) -> None:
    interrogees: list[str] = []

    async def _query_points(*, collection_name, query, **_kwargs):
        interrogees.append(collection_name)
        assert len(query) == DIM
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    score=0.82,
                    payload={"text": "Dosage 350 kg", "document_name": "g.md"},
                )
            ]
        )

    monkeypatch.setattr(rag_service.qdrant_client, "query_points", _query_points)
    hits = await rag_service.search_context("dosage béton poteau")

    assert interrogees == ["connaissances_prosartisan_gemini_1536"]
    assert hits[0]["score"] == 0.82
    assert gemini_vecteurs[0]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"


@pytest.mark.asyncio
async def test_sans_cle_gemini_repli_lexical(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "gemini")
    assert rag_service._is_embedding_mock_mode() is True
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-cle-gemini-test")
    assert rag_service._is_embedding_mock_mode() is False


@pytest.mark.asyncio
async def test_collection_creee_a_la_dimension_gemini(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_embedding_dimensions", DIM)
    creer = AsyncMock()
    monkeypatch.setattr(
        rag_service.qdrant_client, "collection_exists", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(rag_service.qdrant_client, "create_collection", creer)

    await rag_service.ensure_collection()

    kwargs = creer.await_args.kwargs
    assert kwargs["collection_name"] == "connaissances_prosartisan_gemini_1536"
    assert kwargs["vectors_config"].size == DIM


@pytest.mark.asyncio
async def test_collection_d_une_autre_dimension_signalee(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_embedding_dimensions", DIM)
    info = SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(vectors=SimpleNamespace(size=1024))
        )
    )
    monkeypatch.setattr(
        rag_service.qdrant_client, "collection_exists", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        rag_service.qdrant_client, "get_collection", AsyncMock(return_value=info)
    )
    with caplog.at_level(logging.ERROR):
        await rag_service.ensure_collection()
    assert "réindexer" in caplog.text


# ── Ingestion ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_changer_de_modele_reindexe_le_corpus(
    tmp_path, monkeypatch, gemini_vecteurs
) -> None:
    (tmp_path / "guide_beton.md").write_text(
        "# Béton\nDosage du béton armé à 350 kg/m3.", encoding="utf-8"
    )
    monkeypatch.setattr(rag_service, "ensure_collection", AsyncMock())
    collections: list[str] = []

    async def _upsert(*, collection_name, points):
        collections.append(collection_name)
        assert all(len(p.vector) == DIM for p in points)

    monkeypatch.setattr(rag_service.qdrant_client, "upsert", _upsert)
    monkeypatch.setattr(rag_service.qdrant_client, "delete", AsyncMock())

    # Manifeste d'une indexation Mistral antérieure (sans champ collection)
    from ingestion.pipeline import compute_file_sha256

    manifeste = {
        "guide_beton.md": {
            "sha256": compute_file_sha256(str(tmp_path / "guide_beton.md"))
        }
    }
    (tmp_path / ".ingestion_manifest.json").write_text(
        json.dumps(manifeste), encoding="utf-8"
    )

    res = await run_ingestion(docs_dir=str(tmp_path), metier_id=1, secteur_id=1)
    assert res["processed_files"] == 1
    assert collections == ["connaissances_prosartisan_gemini_1536"]
    assert gemini_vecteurs[0]["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"

    # Même modèle, fichier inchangé : sauté
    res2 = await run_ingestion(docs_dir=str(tmp_path), metier_id=1, secteur_id=1)
    assert res2["skipped_files"] == 1
