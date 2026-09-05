"""
Pipeline d'ingestion : Multi-format (PDF / Markdown / Texte) → Chunks sémantiques contextuels → Embeddings réels → Qdrant.

Usage CLI: python -m ingestion.pipeline --docs-dir ./ingestion/documents
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pypdf import PdfReader
from qdrant_client.http.models import PointStruct

from app.config import settings
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)

DEFAULT_OVERLAP_RATIO = 0.12
DEFAULT_CHUNK_SIZE_WORDS = 450
MANIFEST_FILENAME = ".ingestion_manifest.json"

SUPPORTED_EXTENSIONS = (".pdf", ".md", ".markdown", ".txt")

REQUIRED_METADATA_FIELDS = (
    "metier_id",
    "secteur_id",
    "type_document",
    "niveau_expertise",
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def compute_file_sha256(file_path: str) -> str:
    """Calcule l'empreinte SHA-256 d'un fichier pour détecter les modifications."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_text_from_pdf(file_path: str) -> str:
    """Extrait le texte brut d'un fichier PDF."""
    reader = PdfReader(file_path)
    text_chunks: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text_chunks.append(extracted)
    return "\n\n".join(text_chunks)


def extract_text_from_file(file_path: str) -> str:
    """Extrait le contenu textuel selon le format du fichier (.pdf, .md, .txt)."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    if ext in (".md", ".markdown", ".txt"):
        with open(file_path, encoding="utf-8", errors="replace") as f:
            return f.read()
    raise ValueError(
        f"Format non supporté ({ext}). Formats acceptés : {SUPPORTED_EXTENSIONS}"
    )


def _split_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases sans couper au milieu d'une idée."""
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _tail_overlap(sentences: list[str], target_words: int) -> list[str]:
    """Retient les dernières phrases d'un chunk pour amorcer le chevauchement du suivant."""
    overlap: list[str] = []
    words = 0
    for sentence in reversed(sentences):
        if overlap and words >= target_words:
            break
        overlap.insert(0, sentence)
        words += len(sentence.split())
    return overlap


def chunk_text(
    text: str,
    chunk_size_words: int = DEFAULT_CHUNK_SIZE_WORDS,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
) -> list[str]:
    """Découpe un texte en blocs sémantiques (phrases entières) d'environ
    `chunk_size_words` mots, avec un chevauchement d'environ `overlap_ratio`.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    overlap_words_target = max(1, int(chunk_size_words * overlap_ratio))
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())
        if current and current_words + sentence_words > chunk_size_words:
            chunks.append(" ".join(current))
            current = _tail_overlap(current, overlap_words_target)
            current_words = sum(len(s.split()) for s in current)
        current.append(sentence)
        current_words += sentence_words

    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_document_with_context(
    text: str,
    document_name: str,
    chunk_size_words: int = DEFAULT_CHUNK_SIZE_WORDS,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
) -> list[str]:
    """Découpe un document en intégrant le contexte hiérarchique (titres et sections).

    Pour chaque section identifiée (via Markdown # ou titres majeurs), les chunks
    sont préfixés d'une balise contextuelle :
    `[Document: {nom} | Section: {titre}]`
    Ceci optimise considérablement la précision du RAG lors de la recherche vectorielle.
    """
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_section = "Introduction / Généralités"
    current_lines: list[str] = []

    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            if current_lines:
                sections.append((current_section, current_lines))
                current_lines = []
            current_section = match.group(2).strip()
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_section, current_lines))

    # Si aucune section Markdown n'a été détectée, utiliser le découpage standard avec en-tête global
    if len(sections) <= 1 and not any(_HEADING_RE.match(line) for line in lines):
        raw_chunks = chunk_text(text, chunk_size_words, overlap_ratio)
        doc_label = os.path.splitext(document_name)[0].replace("_", " ").title()
        return [f"[Document: {doc_label}]\n{chunk}" for chunk in raw_chunks]

    all_chunks: list[str] = []
    doc_label = os.path.splitext(document_name)[0].replace("_", " ").title()

    for section_title, sec_lines in sections:
        sec_text = "\n".join(sec_lines).strip()
        if not sec_text:
            continue
        sec_chunks = chunk_text(sec_text, chunk_size_words, overlap_ratio)
        for chunk in sec_chunks:
            header = f"[Document: {doc_label} > Section: {section_title}]\n"
            all_chunks.append(f"{header}{chunk}")

    return all_chunks


def load_metadata(docs_dir: str) -> dict[str, Any]:
    """Charge les métadonnées par fichier depuis metadata.json (s'il existe)."""
    meta_path = os.path.join(docs_dir, "metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Échec de lecture de %s: %s", meta_path, exc)
    return {}


def load_manifest(docs_dir: str) -> dict[str, Any]:
    """Charge le manifeste des fichiers déjà ingérés (.ingestion_manifest.json)."""
    manifest_path = os.path.join(docs_dir, MANIFEST_FILENAME)
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Échec de lecture du manifeste %s: %s", manifest_path, exc)
    return {}


def save_manifest(docs_dir: str, manifest: dict[str, Any]) -> None:
    """Sauvegarde l'état d'indexation dans le fichier manifeste."""
    manifest_path = os.path.join(docs_dir, MANIFEST_FILENAME)
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.warning("Impossible d'écrire le manifeste %s: %s", manifest_path, exc)


def resolve_and_validate_metadata(
    filename: str,
    overrides_by_file: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    """Fusionne les métadonnées par fichier avec les valeurs par défaut du batch,
    puis vérifie que les champs obligatoires sont bien renseignés et cohérents.
    """
    merged = {**defaults, **overrides_by_file.get(filename, {})}

    manquants = [
        field for field in REQUIRED_METADATA_FIELDS if merged.get(field) in (None, "")
    ]
    if manquants:
        raise ValueError(
            f"{filename} : métadonnées obligatoires manquantes ({', '.join(manquants)})."
        )

    for field in ("metier_id", "secteur_id"):
        try:
            merged[field] = int(merged[field])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{filename} : '{field}' doit être un identifiant numérique."
            ) from exc
        if merged[field] <= 0:
            raise ValueError(f"{filename} : '{field}' doit être un entier positif.")

    merged["type_document"] = str(merged["type_document"]).strip()
    merged["niveau_expertise"] = str(merged["niveau_expertise"]).strip()
    return merged


def _point_id(document_name: str, chunk_index: int) -> str:
    """ID Qdrant déterministe basé sur le nom du fichier et l'index du chunk."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"prosartisan::{document_name}::{chunk_index}")
    )


async def run_ingestion(
    docs_dir: str = "./ingestion/documents",
    metier_id: int | None = 1,
    secteur_id: int | None = 1,
    type_document: str = "guide_technique",
    niveau_expertise: str = "intermédiaire",
    force_reindex: bool = False,
    batch_size: int = 50,
) -> dict[str, Any]:
    """Exécute l'ingestion complète des documents (.pdf, .md, .txt) vers Qdrant.

    Gère la déduplication par hash SHA-256 (saut des fichiers inchangés sauf si `force_reindex`),
    le découpage sémantique contextuel, et l'indexation par lots avec embeddings réels.
    """
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir, exist_ok=True)
        return {
            "status": "created_directory",
            "processed_files": 0,
            "skipped_files": 0,
            "ingested_chunks": 0,
            "erreurs": [],
        }

    await rag_service.ensure_collection()

    overrides_by_file = load_metadata(docs_dir)
    manifest = load_manifest(docs_dir)
    defaults = {
        "metier_id": metier_id,
        "secteur_id": secteur_id,
        "type_document": type_document,
        "niveau_expertise": niveau_expertise,
    }

    all_files = sorted(
        f
        for f in os.listdir(docs_dir)
        if any(f.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)
        and not f.startswith(".")
    )

    total_chunks = 0
    processed_files = 0
    skipped_files = 0
    erreurs: list[str] = []

    for filename in all_files:
        path = os.path.join(docs_dir, filename)

        try:
            meta = resolve_and_validate_metadata(filename, overrides_by_file, defaults)
        except ValueError as exc:
            erreurs.append(str(exc))
            continue

        try:
            file_sha = compute_file_sha256(path)
        except Exception as exc:
            erreurs.append(f"{filename} : calcul du hash impossible ({exc}).")
            continue

        # Vérification d'incrémentalité : ignorer si déjà indexé sans modification
        prev_entry = manifest.get(filename)
        if not force_reindex and prev_entry and prev_entry.get("sha256") == file_sha:
            logger.info("Fichier inchangé, saut de l'ingestion : %s", filename)
            skipped_files += 1
            continue

        try:
            text = extract_text_from_file(path)
        except Exception as exc:
            erreurs.append(f"{filename} : extraction de texte impossible ({exc}).")
            continue

        chunks = chunk_document_with_context(text, filename)
        if not chunks:
            erreurs.append(f"{filename} : aucun texte exploitable extrait.")
            continue

        points: list[PointStruct] = []
        for idx, chunk in enumerate(chunks):
            try:
                vector = await rag_service.get_embedding(chunk)
            except Exception as exc:
                erreurs.append(f"{filename} : échec de génération d'embedding ({exc}).")
                break
            payload = {
                "text": chunk,
                "document_name": filename,
                "chunk_index": idx,
                "sha256": file_sha,
                **meta,
            }
            points.append(
                PointStruct(id=_point_id(filename, idx), vector=vector, payload=payload)
            )

        if len(points) != len(chunks):
            # Erreur survenue pendant la génération d'embeddings
            continue

        # Upsert par lots vers Qdrant
        index_error = False
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            try:
                await rag_service.qdrant_client.upsert(
                    collection_name=settings.qdrant_collection,
                    points=batch,
                )
            except Exception as exc:
                erreurs.append(f"{filename} : échec de l'indexation Qdrant ({exc}).")
                index_error = True
                break

        if index_error:
            continue

        # Mise à jour du manifeste
        manifest[filename] = {
            "sha256": file_sha,
            "chunks_count": len(chunks),
            "last_ingested_at": datetime.now(UTC).isoformat(),
            "metadata": meta,
        }
        total_chunks += len(chunks)
        processed_files += 1
        logger.info("Document ingéré : %s (%d chunks).", filename, len(chunks))

    save_manifest(docs_dir, manifest)

    status_val = "success"
    if erreurs and processed_files == 0 and skipped_files == 0:
        status_val = "error"
    elif erreurs:
        status_val = "partial"

    return {
        "status": status_val,
        "processed_files": processed_files,
        "skipped_files": skipped_files,
        "ingested_chunks": total_chunks,
        "erreurs": erreurs,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Pipeline d'ingestion ProsArtisan")
    parser.add_argument(
        "--docs-dir",
        default="./ingestion/documents",
        help="Dossier contenant les documents",
    )
    parser.add_argument(
        "--metier-id", type=int, default=1, help="ID du métier par défaut"
    )
    parser.add_argument(
        "--secteur-id", type=int, default=1, help="ID du secteur par défaut"
    )
    parser.add_argument("--type-document", default="guide_technique")
    parser.add_argument("--niveau-expertise", default="intermédiaire")
    parser.add_argument(
        "--force-reindex",
        action="store_true",
        help="Forcer la ré-ingestion même si le fichier est inchangé",
    )
    args = parser.parse_args()

    resultat = asyncio.run(
        run_ingestion(
            docs_dir=args.docs_dir,
            metier_id=args.metier_id,
            secteur_id=args.secteur_id,
            type_document=args.type_document,
            niveau_expertise=args.niveau_expertise,
            force_reindex=args.force_reindex,
        )
    )
    print(f"Ingestion terminée: {resultat}")
