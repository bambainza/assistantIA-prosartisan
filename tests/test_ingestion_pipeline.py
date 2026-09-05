"""Tests du pipeline d'ingestion : multi-format, métadonnées obligatoires, embeddings réels,
découpage sémantique contextuel, déduplication SHA-256 et idempotence Qdrant.
"""

import json

import pytest

from app.services.rag_service import rag_service
from ingestion.pipeline import (
    _point_id,
    chunk_document_with_context,
    compute_file_sha256,
    extract_text_from_file,
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
    """Ré-ingérer le même document doit produire les mêmes ID de points Qdrant."""
    assert _point_id("guide.pdf", 0) == _point_id("guide.pdf", 0)
    assert _point_id("guide.pdf", 0) != _point_id("guide.pdf", 1)
    assert _point_id("guide.pdf", 0) != _point_id("autre.pdf", 0)


# ── Multi-format & Chunking Contextuel ─────────────────────────────────────


def test_extract_text_from_markdown_and_txt(tmp_path):
    md_file = tmp_path / "guide.md"
    md_file.write_text("# Titre Markdown\nContenu technique ici.", encoding="utf-8")
    assert "Titre Markdown" in extract_text_from_file(str(md_file))

    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("Texte brut d'artisan.", encoding="utf-8")
    assert "Texte brut d'artisan." in extract_text_from_file(str(txt_file))


def test_extract_text_unsupported_format_raises(tmp_path):
    bin_file = tmp_path / "archive.zip"
    bin_file.write_bytes(b"PK000")
    with pytest.raises(ValueError, match="Format non supporté"):
        extract_text_from_file(str(bin_file))


def test_chunk_document_with_context_injects_section_headers():
    doc_text = (
        "# Guide Maçonnerie\n"
        "Introduction générale aux travaux de maçonnerie.\n\n"
        "## Dosage du Béton\n"
        "Pour le béton armé ordinaire dosé à 350 kg/m3, utiliser 7 sacs de ciment.\n\n"
        "## Ferraillage des Semelles\n"
        "Les semelles isolées requièrent des barres HA 10 et un enrobage de 4 cm."
    )
    chunks = chunk_document_with_context(doc_text, "guide_maconnerie.md")
    assert len(chunks) >= 2
    assert any(
        "[Document: Guide Maconnerie > Section: Dosage du Béton]" in c for c in chunks
    )
    assert any(
        "[Document: Guide Maconnerie > Section: Ferraillage des Semelles]" in c
        for c in chunks
    )


def test_compute_file_sha256(tmp_path):
    file1 = tmp_path / "test1.txt"
    file1.write_text("Hello World", encoding="utf-8")
    h1 = compute_file_sha256(str(file1))
    assert isinstance(h1, str) and len(h1) == 64

    file2 = tmp_path / "test2.txt"
    file2.write_text("Hello World", encoding="utf-8")
    assert compute_file_sha256(str(file2)) == h1


# ── run_ingestion ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_ingestion_cree_le_dossier_absent(tmp_path):
    docs_dir = tmp_path / "documents_absents"
    res = await run_ingestion(docs_dir=str(docs_dir))

    assert res["status"] == "created_directory"
    assert docs_dir.exists()


@pytest.mark.asyncio
async def test_run_ingestion_multi_format_et_deduplication(tmp_path, monkeypatch):
    """Vérifie l'ingestion de Markdown et l'indexation incrémentale (saut des fichiers inchangés)."""
    (tmp_path / "guide_maconnerie.md").write_text(
        "# Maçonnerie\nDosage du béton armé à 350kg/m3.", encoding="utf-8"
    )

    monkeypatch.setattr(rag_service, "ensure_collection", lambda: _async_none())

    upserted_points = []

    async def fake_upsert(*, collection_name, points):
        upserted_points.extend(points)

    monkeypatch.setattr(rag_service.qdrant_client, "upsert", fake_upsert)

    # 1ère passe : Ingestion réussie
    res1 = await run_ingestion(docs_dir=str(tmp_path), metier_id=1, secteur_id=1)
    assert res1["status"] == "success"
    assert res1["processed_files"] == 1
    assert res1["skipped_files"] == 0
    assert res1["ingested_chunks"] >= 1
    assert len(upserted_points) == res1["ingested_chunks"]
    assert upserted_points[0].payload["document_name"] == "guide_maconnerie.md"
    assert "sha256" in upserted_points[0].payload

    # 2ème passe : Inchangé -> doit être sauté grâce au hash SHA-256
    upserted_points.clear()
    res2 = await run_ingestion(docs_dir=str(tmp_path), metier_id=1, secteur_id=1)
    assert res2["status"] == "success"
    assert res2["processed_files"] == 0
    assert res2["skipped_files"] == 1
    assert res2["ingested_chunks"] == 0
    assert len(upserted_points) == 0

    # 3ème passe avec force_reindex=True -> doit ré-ingérer
    res3 = await run_ingestion(
        docs_dir=str(tmp_path), metier_id=1, secteur_id=1, force_reindex=True
    )
    assert res3["status"] == "success"
    assert res3["processed_files"] == 1
    assert res3["skipped_files"] == 0
    assert res3["ingested_chunks"] >= 1


@pytest.mark.asyncio
async def test_run_ingestion_collecte_les_erreurs_sans_planter(tmp_path, monkeypatch):
    """Un fichier avec des métadonnées invalides est ignoré (erreur journalisée),
    sans bloquer le traitement des autres fichiers du dossier."""
    (tmp_path / "invalide.md").write_text("# Invalide\nTexte test.", encoding="utf-8")
    (tmp_path / "metadata.json").write_text(
        json.dumps({"invalide.md": {"metier_id": "pas-un-nombre"}}), encoding="utf-8"
    )

    monkeypatch.setattr(rag_service, "ensure_collection", lambda: _async_none())

    res = await run_ingestion(docs_dir=str(tmp_path), metier_id=1, secteur_id=1)

    assert res["status"] == "error"
    assert res["processed_files"] == 0
    assert res["ingested_chunks"] == 0
    assert len(res["erreurs"]) == 1
    assert "invalide.md" in res["erreurs"][0]


async def _async_none():
    return None
