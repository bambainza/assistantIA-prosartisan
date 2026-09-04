"""Tests du pipeline d'ingestion : métadonnées obligatoires, embeddings réels,
chevauchement sémantique et idempotence des points Qdrant.
"""

import json

import pytest

from app.services.rag_service import rag_service
from ingestion.pipeline import (
    _point_id,
    resolve_and_validate_metadata,
    run_ingestion,
)

_DEFAULTS = {
    "metier_id": 1,
    "secteur_id": 1,
    "type_document": "guide_technique",
    "niveau_expertise": "intermédiaire",
}


# ── resolve_and_validate_metadata ──────────────────────────────────────────


def test_metadata_valide_avec_defauts():
    meta = resolve_and_validate_metadata("guide.pdf", {}, _DEFAULTS)
    assert meta["metier_id"] == 1
    assert meta["type_document"] == "guide_technique"


def test_metadata_override_par_fichier_prevaut():
    overrides = {"guide.pdf": {"metier_id": 2, "type_document": "norme_officielle"}}
    meta = resolve_and_validate_metadata("guide.pdf", overrides, _DEFAULTS)
    assert meta["metier_id"] == 2
    assert meta["type_document"] == "norme_officielle"
    assert meta["secteur_id"] == 1  # non surchargé : valeur par défaut conservée


def test_metadata_champ_obligatoire_manquant_leve_erreur():
    defauts_incomplets = {**_DEFAULTS, "niveau_expertise": ""}
    with pytest.raises(ValueError, match="niveau_expertise"):
        resolve_and_validate_metadata("guide.pdf", {}, defauts_incomplets)


def test_metadata_metier_id_non_numerique_leve_erreur():
    overrides = {"guide.pdf": {"metier_id": "maconnerie"}}
    with pytest.raises(ValueError, match="identifiant numérique"):
        resolve_and_validate_metadata("guide.pdf", overrides, _DEFAULTS)


def test_metadata_metier_id_negatif_leve_erreur():
    overrides = {"guide.pdf": {"metier_id": -1}}
    with pytest.raises(ValueError, match="positif"):
        resolve_and_validate_metadata("guide.pdf", overrides, _DEFAULTS)


# ── _point_id ───────────────────────────────────────────────────────────────


def test_point_id_deterministe():
    """Ré-ingérer le même document doit produire les mêmes ID de points Qdrant
    (mise à jour des points existants, pas de doublons)."""
    assert _point_id("guide.pdf", 0) == _point_id("guide.pdf", 0)
    assert _point_id("guide.pdf", 0) != _point_id("guide.pdf", 1)
    assert _point_id("guide.pdf", 0) != _point_id("autre.pdf", 0)


# ── run_ingestion ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_ingestion_cree_le_dossier_absent(tmp_path):
    docs_dir = tmp_path / "documents_absents"
    res = await run_ingestion(docs_dir=str(docs_dir))

    assert res["status"] == "created_directory"
    assert docs_dir.exists()


@pytest.mark.asyncio
async def test_run_ingestion_utilise_les_embeddings_de_rag_service(
    tmp_path, monkeypatch
):
    """Les vecteurs indexés doivent provenir de rag_service.get_embedding (mode
    mock inclus), plus jamais d'un vecteur factice codé en dur."""
    (tmp_path / "guide.pdf").write_bytes(b"%PDF-1.4 contenu factice")

    monkeypatch.setattr(
        "ingestion.pipeline.extract_text_from_pdf",
        lambda _path: "Première phrase du guide. Deuxième phrase du guide.",
    )
    monkeypatch.setattr(rag_service, "ensure_collection", lambda: _async_none())

    upserted = {}

    async def fake_upsert(*, collection_name, points):
        upserted["collection_name"] = collection_name
        upserted["points"] = points

    monkeypatch.setattr(rag_service.qdrant_client, "upsert", fake_upsert)

    res = await run_ingestion(docs_dir=str(tmp_path), metier_id=1, secteur_id=1)

    assert res["status"] == "success"
    assert res["processed_files"] == 1
    assert res["ingested_chunks"] >= 1
    assert res["erreurs"] == []

    points = upserted["points"]
    assert len(points) == res["ingested_chunks"]
    # Mode mock (OPENAI_API_KEY placeholder) -> embedding nul, mais bien issu
    # de rag_service.get_embedding (cache + logique partagée avec la requête).
    assert points[0].vector == [0.0] * 1536
    assert points[0].payload["metier_id"] == 1
    assert points[0].payload["document_name"] == "guide.pdf"


@pytest.mark.asyncio
async def test_run_ingestion_metadata_json_par_fichier(tmp_path, monkeypatch):
    (tmp_path / "guide_elec.pdf").write_bytes(b"%PDF-1.4 contenu factice")
    (tmp_path / "metadata.json").write_text(
        json.dumps({"guide_elec.pdf": {"metier_id": 2}}), encoding="utf-8"
    )

    monkeypatch.setattr(
        "ingestion.pipeline.extract_text_from_pdf",
        lambda _path: "Une phrase suffisante pour former un chunk complet.",
    )
    monkeypatch.setattr(rag_service, "ensure_collection", lambda: _async_none())

    upserted = {}

    async def fake_upsert(*, collection_name, points):
        upserted["points"] = points

    monkeypatch.setattr(rag_service.qdrant_client, "upsert", fake_upsert)

    res = await run_ingestion(docs_dir=str(tmp_path), metier_id=1, secteur_id=1)

    assert res["status"] == "success"
    assert upserted["points"][0].payload["metier_id"] == 2  # surchargé, pas 1


@pytest.mark.asyncio
async def test_run_ingestion_collecte_les_erreurs_sans_planter(tmp_path, monkeypatch):
    """Un fichier avec des métadonnées invalides est ignoré (erreur journalisée),
    sans bloquer le traitement des autres fichiers du dossier."""
    (tmp_path / "invalide.pdf").write_bytes(b"%PDF-1.4 contenu factice")
    (tmp_path / "metadata.json").write_text(
        json.dumps({"invalide.pdf": {"metier_id": "pas-un-nombre"}}), encoding="utf-8"
    )

    monkeypatch.setattr(rag_service, "ensure_collection", lambda: _async_none())

    res = await run_ingestion(docs_dir=str(tmp_path), metier_id=1, secteur_id=1)

    assert res["status"] == "error"
    assert res["processed_files"] == 0
    assert res["ingested_chunks"] == 0
    assert len(res["erreurs"]) == 1
    assert "invalide.pdf" in res["erreurs"][0]


async def _async_none():
    return None
